# heard

Speech-to-text for Linux desktop via an anonymous web transcription endpoint. No local models, no API keys, no login.

## How it works
1. Records mic (`pw-record`), toggle single key
2. Converts to mp3, POSTs to anonymous endpoint through a stealth headless browser session (Cloudflare-proof)
3. Pastes transcript into focused window (`wl-copy` + `ydotool`)

## Usage
```bash
scripts/dictate-heard.sh   # call from your WM shortcut (e.g. F8)
```
First press: starts recording. Second press: stop → transcribe → paste.

## Requirements
Arch/CachyOS: `pacman -S ydotool wl-clipboard ffmpeg python-playwright` + `playwright install chromium` + systemd `ydotoold`

## Rate limits
Anonymous tier ≈ 3 transcriptions/min. Error surfaces via desktop notification.

## License
MIT

## Hermes Agent integration
`heard` works as Hermes Agent's system-wide STT provider:
```bash
# ~/.hermes/.env
HERMES_LOCAL_STT_COMMAND=/path/to/heard-stt-adapter {input_path} {model} {output_dir} {language}
# config.yaml
stt: { enabled: true, provider: local_command, language: pt }
```
All Hermes voice messages (Telegram, WhatsApp, gateway, CLI /voice) transcribe via heard.
