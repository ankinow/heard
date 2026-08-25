"""heard test suite — unit (mocked, protocol v2.x) + integration (network, opt-in).

v2.2: testes de transcribe rodam contra o PROTOCOLO do worker (stdin/stdout
JSON), com um fake worker injetado via HEARD_WORKER_SCRIPT. Não dependem de
playwright nem de rede — cobrem o pool, o bootstrap e o mapeamento de erro.
"""
import json, os, sys, textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import heard


# ---------- fake worker: fala o mesmo protocolo stdin/stdout do real ----------

def _write_fake_worker(tmp_path, result=None, error=None):
    """Worker fake que imprime ready e responde cada request com payload fixo."""
    payload = (json.dumps({"error": error}) if error is not None
               else json.dumps({"result": result}))
    script = tmp_path / "fake_worker.py"
    script.write_text(textwrap.dedent(f"""
        import json, sys
        lang = sys.argv[1] if len(sys.argv) > 1 else "pt"
        print(json.dumps({{"ready": True}}), flush=True)
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            req = json.loads(line)
            assert isinstance(req.get("b64"), str)
            print({payload!r}, flush=True)
    """))
    return str(script)


@pytest.fixture
def fake_pool(monkeypatch, tmp_path):
    """Instala um pool fresco apontando pro fake worker; limpa no fim."""
    def install(result=None, error=None):
        script = _write_fake_worker(tmp_path, result=result, error=error)
        monkeypatch.setenv("HEARD_WORKER_SCRIPT", script)
        monkeypatch.setenv("HEARD_POOL", "2")
        import importlib
        importlib.reload(heard)  # HEARD_POOL/UPSTREAM são lidos no import
        heard._pool = None  # força pool novo
        return script

    yield install
    heard._pool = None


# ---------- unit: wav_to_mp3 (ffmpeg real) ----------

def test_wav_to_mp3_converts(tmp_path):
    import subprocess
    wav = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=0.3",
                    str(wav)], capture_output=True, check=True)
    mp3, mime, name = heard.wav_to_mp3(str(wav))
    assert Path(mp3).exists() and Path(mp3).stat().st_size > 500
    assert mime == "audio/mpeg" and name == "audio.mp3"
    os.unlink(mp3)


def test_wav_to_mp3_fallback_on_ffmpeg_fail(tmp_path):
    bad = tmp_path / "bad.wav"; bad.write_bytes(b"not-a-wav")
    mp3, mime, name = heard.wav_to_mp3(str(bad))
    assert mp3 == str(bad) and mime == "audio/wav"  # fallback p/ original


# ---------- unit: transcribe via protocolo (fake worker subprocess) ----------

def _make_wav(tmp_path):
    import wave
    path = tmp_path / "ok.wav"
    w = wave.open(str(path), "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(b"\x00\x00" * 3200); w.close()
    return str(path)


def test_transcribe_success(fake_pool, tmp_path):
    fake_pool(result={"status": 200, "text": "olá mundo"})
    out = heard.transcribe(_make_wav(tmp_path), "pt")
    assert out == "olá mundo"


def test_transcribe_429_raises(fake_pool, tmp_path):
    fake_pool(result={"status": 429, "text": None})
    with pytest.raises(RuntimeError, match="429"):
        heard.transcribe(_make_wav(tmp_path), "pt")


def test_transcribe_worker_error_line(fake_pool, tmp_path):
    fake_pool(error="upstream exploded")
    with pytest.raises(RuntimeError, match="upstream exploded"):
        heard.transcribe(_make_wav(tmp_path), "pt")


def test_transcribe_upstream_url_env(monkeypatch):
    """HEARD_UPSTREAM_URL é consumida pelo lib no import (worker real que usa rede)."""
    monkeypatch.setenv("HEARD_UPSTREAM_URL", "https://example.invalid")
    import importlib
    importlib.reload(heard)
    assert heard.UPSTREAM_URL == "https://example.invalid"


def test_pool_reuses_live_workers(fake_pool):
    """Pool cria até POOL_SIZE workers vivos; acquire extra REUTILIZA em vez de spawnar."""
    fake_pool(result={"status": 200, "text": "x"})
    a = heard._get_pool().acquire()
    b = heard._get_pool().acquire()
    c = heard._get_pool().acquire()  # 3º com POOL_SIZE=2 -> reutiliza
    live = [w for w in heard._pool.workers if w.proc.poll() is None]
    assert len(live) == 2 and c in (a, b)


# ---------- integration (real network + playwright) — HEARD_INTEGRATION=1 ----------
@pytest.mark.skipif(os.environ.get("HEARD_INTEGRATION") != "1",
                    reason="network test (precisa playwright + chromium)")
def test_integration_real_endpoint(tmp_path):
    import subprocess
    wav = tmp_path / "real.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi",
                    "-i", "sine=frequency=300:duration=1", str(wav)],
                   capture_output=True, check=True)
    out = heard.transcribe(str(wav), "pt")
    assert isinstance(out, str)  # 200 com algum texto (tone = lixo ok)
