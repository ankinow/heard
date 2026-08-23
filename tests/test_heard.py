"""heard test suite — unit (mocked) + integration (network, opt-in)."""
import base64, sys, os
import unittest.mock as m
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
import heard

# ---------- unit: wav_to_mp3 ----------
def test_wav_to_mp3_converts(tmp_path):
    wav = tmp_path / "a.wav"
    # wav mínimo válido via ffmpeg
    import subprocess
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i","sine=frequency=440:duration=0.3",
                    str(wav)], capture_output=True, check=True)
    mp3, mime, name = heard.wav_to_mp3(str(wav))
    assert Path(mp3).exists() and Path(mp3).stat().st_size > 500
    assert mime == "audio/mpeg" and name == "audio.mp3"
    os.unlink(mp3)

def test_wav_to_mp3_fallback_on_ffmpeg_fail(tmp_path):
    bad = tmp_path / "bad.wav"; bad.write_bytes(b"not-a-wav")
    mp3, mime, name = heard.wav_to_mp3(str(bad))
    assert mp3 == str(bad) and mime == "audio/wav"  # fallback p/ original

# ---------- unit: transcribe com browser mockado ----------
class FakePage:
    def __init__(self, result): self._r = result; self.goto_calls = []
    def goto(self, url, **kw): self.goto_calls.append(url)
    def wait_for_timeout(self, ms): pass
    def evaluate(self, js, arg): return self._r

class FakeCtx:
    def __init__(self, page): self._p = page
    def new_page(self): return self._p
    def close(self): pass
class FakeBrowser:
    def __init__(self, ctx): self._c = ctx
    def new_context(self, **kw): return self._c
    def close(self): pass

class _CM:
    def __init__(self, fake): self.f = fake
    def __enter__(self): return self.f
    def __exit__(self, *a): return False

def _make_fake(result):
    class C:
        def launch(self, **kw): return FakeBrowser(FakeCtx(FakePage(result)))
    class FakePW:
        @property
        def chromium(self): return C()
    return FakePW()

@pytest.fixture
def patch_playwright(monkeypatch):
    def _install(result):
        monkeypatch.setattr("playwright.sync_api.sync_playwright",
                            lambda: _CM(_make_fake(result)))
    return _install

def test_transcribe_success(patch_playwright, tmp_path):
    wav = tmp_path / "ok.wav"
    import wave, struct
    w = wave.open(str(wav),"wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(b"\x00\x00"*3200); w.close()
    patch_playwright({"status":200,"text":"olá mundo"})
    out = heard.transcribe(str(wav), "pt")
    assert out == "olá mundo"

def test_transcribe_429_raises(patch_playwright, tmp_path):
    wav = tmp_path / "ok.wav"
    import wave
    w = wave.open(str(wav),"wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(b"\x00\x00"*3200); w.close()
    patch_playwright({"status":429,"text":None})
    with pytest.raises(RuntimeError, match="429"):
        heard.transcribe(str(wav), "pt")

def test_transcribe_upstream_url_env(patch_playwright, monkeypatch, tmp_path):
    wav = tmp_path / "ok.wav"
    import wave
    w = wave.open(str(wav),"wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(b"\x00\x00"*3200); w.close()
    monkeypatch.setenv("HEARD_UPSTREAM_URL","https://example.invalid")
    captured = {}
    real_goto = FakePage.goto
    def goto_cap(self, url, **kw):
        captured["url"] = url; return real_goto(self, url, **kw)
    FakePage.goto = goto_cap
    monkeypatch.setattr("playwright.sync_api.sync_playwright",
                        lambda: _CM(_make_fake({"status":200,"text":"x"})))
    try:
        heard.transcribe(str(wav),"pt")
    finally:
        FakePage.goto = real_goto
    assert captured["url"].startswith("https://example.invalid")

# ---------- integration (real network) — rodar com HEARD_INTEGRATION=1 ----------
@pytest.mark.skipif(os.environ.get("HEARD_INTEGRATION")!="1", reason="network test")
def test_integration_real_endpoint(tmp_path):
    import subprocess
    wav = tmp_path / "real.wav"
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i","sine=frequency=300:duration=1",str(wav)],
                   capture_output=True, check=True)
    out = heard.transcribe(str(wav), "pt")
    assert isinstance(out, str)  # 200 com algum texto (tone = lixo ok)

