#!/usr/bin/env python3
"""heard v2.2 — anonymous STT with subprocess session-pool.

Rate-limit empiria (2026-08-23): key = session cookie, not IP.
~1 transcription/min per session; fresh session = fresh quota.
Pool of worker subprocesses rotates sessions; each worker handles
N requests then is recycled. No threads touching Playwright greenlets.

v2.2: HEARD_WORKER_SCRIPT env override — aponta o pool para outro script
de worker (mesmo protocolo stdin/stdout). Usado pelos testes unitários
(fake worker sem playwright/rede) e por quem quiser trocar o upstream.
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import atexit

os.environ.setdefault("GDK_BACKEND", "wayland")

UPSTREAM_URL = os.environ.get("HEARD_UPSTREAM_URL", "https://chatgpt.com")
POOL_SIZE = int(os.environ.get("HEARD_POOL", "3"))
REQUESTS_PER_SESSION = 4  # reciclar antes do limite ~1/min? não: quota é por tempo.
# Empiria: limite temporal por sessão (~60s). Pool dá N sessões => N ditados/min.


def _worker_script() -> str:
    """Caminho do worker resolvido em tempo de uso (permite override em runtime)."""
    return os.environ.get(
        "HEARD_WORKER_SCRIPT",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "heard_worker.py"),
    )


class Worker:
    def __init__(self, lang="pt"):
        self.proc = subprocess.Popen(
            [sys.executable, _worker_script(), lang],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1)
        ready = self.proc.stdout.readline()  # consome {"ready": true}
        if "ready" not in ready:
            raise RuntimeError(f"worker bootstrap failed: {ready[:100]}")

    def transcribe(self, b64, mime, name, lang):
        self.proc.stdin.write(json.dumps(
            {"b64": b64, "mime": mime, "name": name}) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("worker died")
        resp = json.loads(line)
        if "error" in resp:
            raise RuntimeError(resp["error"])
        r = resp["result"]
        if r["status"] == 200 and r["text"]:
            return r["text"]
        raise RuntimeError(f"HTTP {r['status']}")

    def close(self):
        try:
            self.proc.stdin.close(); self.proc.kill()
        except Exception:
            pass


class HeardPool:
    def __init__(self):
        self.workers: list[Worker] = []
        self.idx = 0

    def acquire(self) -> Worker:
        live = [w for w in self.workers if w.proc.poll() is None]
        if len(live) < POOL_SIZE:
            w = Worker()
            self.workers.append(w)
            return w
        self.idx = (self.idx + 1) % len(live)
        return live[self.idx]


_pool: HeardPool | None = None


def _get_pool() -> HeardPool:
    global _pool
    if _pool is None:
        _pool = HeardPool()
        atexit.register(_shutdown)
    return _pool


def _shutdown():
    if _pool:
        for w in _pool.workers:
            w.close()


def wav_to_mp3(wav_path):
    mp3 = tempfile.mktemp(suffix=".mp3")
    r = subprocess.run(["ffmpeg", "-y", "-i", wav_path,
                        "-codec:a", "libmp3lame", "-qscale:a", "4", mp3],
                       capture_output=True)
    if r.returncode != 0:
        return wav_path, "audio/wav", "audio.wav"
    return mp3, "audio/mpeg", "audio.mp3"


def transcribe(audio_path: str, lang: str = "pt") -> str:
    if audio_path.endswith(".wav"):
        up, mime, name = wav_to_mp3(audio_path)
    else:
        up, mime, name = audio_path, "audio/mpeg", "audio.mp3"
    b64 = base64.b64encode(open(up, "rb").read()).decode()
    if up != audio_path:
        os.unlink(up)
    return _get_pool().acquire().transcribe(b64, mime, name, lang)


if __name__ == "__main__":
    print(transcribe(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "pt"))
