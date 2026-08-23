#!/usr/bin/env python3
"""heard — speech-to-text via anonymous web service. No local models."""
import base64, sys, json, tempfile, subprocess, os

def wav_to_mp3(wav_path):
    mp3 = tempfile.mktemp(suffix=".mp3")
    r = subprocess.run(["ffmpeg","-y","-i",wav_path,"-codec:a","libmp3lame","-qscale:a","4",mp3],
                       capture_output=True)
    if r.returncode != 0: return wav_path, "audio/wav", "audio.wav"
    return mp3, "audio/mpeg", "audio.mp3"

def transcribe(audio_path, lang="pt"):
    """Opens stealth browser, gets anonymous session, POSTs audio. Returns text or raises."""
    from playwright.sync_api import sync_playwright
    if audio_path.endswith(".wav"):
        up, mime, name = wav_to_mp3(audio_path)
    else:
        up, mime, name = audio_path, "audio/mpeg", "audio.mp3"
    b64 = base64.b64encode(open(up,"rb").read()).decode()
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(locale="pt-BR",
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        pg = ctx.new_page()
        pg.goto("https://chatgpt.com", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(6000)
        result = pg.evaluate("""async ([b64, mime, name, lang]) => {
            const bin = atob(b64); const arr = new Uint8Array(bin.length);
            for (let i=0;i<bin.length;i++) arr[i]=bin.charCodeAt(i);
            const fd = new FormData();
            fd.append('file', new Blob([arr], {type: mime}), name);
            fd.append('language', lang);
            const r = await fetch('/backend-anon/transcribe', {method:'POST', body: fd});
            let t; try { t = JSON.parse(await r.text()).text } catch(e){ t=null }
            return {status:r.status, text:t};
        }""", [b64, mime, name, lang])
        b.close()
    if up != audio_path: os.unlink(up)
    if result["status"] == 200 and result["text"]:
        return result["text"]
    raise RuntimeError(f"transcribe failed: HTTP {result['status']} (rate-limit anon ~3/min se 429)")

if __name__ == "__main__":
    print(transcribe(sys.argv[1], sys.argv[2] if len(sys.argv)>2 else "pt"))
