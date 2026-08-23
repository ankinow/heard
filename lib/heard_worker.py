#!/usr/bin/env python3
"""heard session worker — one process per anonymous session. stdin: wav path; stdout: JSON."""
import sys, os, base64, json
os.environ.setdefault("GDK_BACKEND", "wayland")
from playwright.sync_api import sync_playwright

UPSTREAM = os.environ.get("HEARD_UPSTREAM_URL", "https://chatgpt.com")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

def main():
    lang = sys.argv[1] if len(sys.argv) > 1 else "pt"
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(locale="pt-BR", user_agent=UA)
        pg = ctx.new_page()
        pg.goto(UPSTREAM, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(5000)
        print(json.dumps({"ready": True}), flush=True)
        for line in sys.stdin:
            line = line.strip()
            if not line: continue
            try:
                req = json.loads(line)
                b64 = req["b64"]; mime = req["mime"]
                r = pg.evaluate("""async ([b64, mime, name, lang]) => {
                    const bin = atob(b64); const arr = new Uint8Array(bin.length);
                    for (let i=0;i<bin.length;i++) arr[i]=bin.charCodeAt(i);
                    const fd = new FormData();
                    fd.append('file', new Blob([arr], {type: mime}), name);
                    fd.append('language', lang);
                    const r = await fetch('/backend-anon/transcribe', {method:'POST', body: fd});
                    let t=null; try{ t=(await r.json()).text }catch(e){}
                    return {status:r.status, text:t};
                }""", [b64, mime, "a.mp3", lang])
                print(json.dumps({"result": r}), flush=True)
            except Exception as e:
                print(json.dumps({"error": str(e)}), flush=True)
        b.close()

if __name__ == "__main__":
    main()
