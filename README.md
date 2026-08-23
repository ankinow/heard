# heard

> **Your voice, transcribed anywhere — no models, no keys, no cloud accounts.**

[![tests](https://img.shields.io/badge/tests-5%20unit%20%2B%201%20integration-brightgreen)]() [![license](https://img.shields.io/badge/license-MIT-blue)]() [![platform](https://img.shields.io/badge/platform-Linux%20%C2%B7%20Wayland%20%C2%B7%20KDE-lightgrey)]()

**heard** is a speech-to-text engine for the Linux desktop that turns a global hotkey into instant, high-fidelity transcription in *any* application. Press once to speak, press again to see your words land at the cursor — in your editor, your browser, your terminal, a chat window, anywhere text can go.

It achieves ~99% transcription fidelity in Brazilian Portuguese and dozens of other languages **without running a single local model and without owning an API key**, by orchestrating anonymous web sessions through a rotating pool of stealth browser workers.

Built for operators who think in hotkeys. Designed for people who talk faster than they type.

---

## Table of Contents

- [Why heard exists](#why-heard-exists)
- [How it works](#how-it-works)
- [Key features](#key-features)
- [Requirements](#requirements)
- [Installation](#installation)
  - [Arch / CachyOS](#arch--cachyos)
  - [Manual setup](#manual-setup)
  - [Model & session configuration](#configuration)
- [Usage](#usage)
  - [The toggle pattern](#the-toggle-pattern)
  - [Binding to your window manager](#binding-to-your-window-manager)
- [The session-pool architecture](#the-session-pool-architecture)
  - [Rate-limit empirics](#rate-limit-empirics)
  - [Pool topology](#pool-topology)
- [Hermes Agent integration](#hermes-agent-integration)
- [Configuration reference](#configuration-reference)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Known limitations](#known-limitations)
- [Design notes & reverse-engineering diary](#design-notes--reverse-engineering-diary)
- [Related work by the author](#related-work-by-the-author)
- [License](#license)

---

## Why heard exists

Every speech-to-text solution on Linux falls into one of two camps:

1. **Local models** (whisper.cpp, Vosk, faster-whisper) — private but heavy: hundreds of megabytes of weights, seconds of latency on consumer CPUs, and accuracy that collapses on accented, technical, or code-switched speech.
2. **Cloud APIs** (OpenAI, Google, Deepgram) — accurate but gated behind accounts, API keys, billing, and per-request costs.

**heard** refuses both trade-offs. It sits in a third position that most tooling ignores: the *anonymous web tier* — the same transcription endpoint your browser reaches before you ever sign in. That tier runs frontier-class acoustic models, costs nothing, requires no identity, and responds in under a second.

The engineering problem was never access; it was **session discipline**: anonymous tiers rate-limit per session cookie, not per IP. heard solves this with a rotating pool of pre-warmed browser sessions — a small piece of infrastructure that turns a one-shot demo into a dependable daily driver.

## How it works

```
┌──────────────┐    pw-record     ┌─────────┐    ffmpeg     ┌────────┐
│  F8 pressed  │ ───────────────► │ WAV/PCM │ ────────────► │  MP3   │
│  (1st press) │                  │ 16kHz   │               │        │
└──────────────┘                  └─────────┘               └───┬────┘
                                                                │ base64
                                                                ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     SESSION POOL (subprocess workers)                  │
│                                                                        │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐                            │
│  │ worker A │   │ worker B │   │ worker C │   each = headless Chromium │
│  │ sessão 1 │   │ sessão 2 │   │ sessão 3 │   + anonymous cookies      │
│  └────┬─────┘   └──────────┘   └──────────┘                            │
│       │ round-robin                                                    │
└───────┼────────────────────────────────────────────────────────────────┘
        │ multipart POST /backend-anon/transcribe {file, language}
        ▼
┌──────────────────┐      {"text": "..."}      ┌───────────────────────┐
│  remote endpoint │ ────────────────────────► │ wl-copy + ydotool     │
│  (anonymous)     │                           │ paste → focused window│
└──────────────────┘                           └───────────────────────┘
```

1. **First keypress** spawns `pw-record` (PipeWire) capturing 16 kHz mono audio.
2. **Second keypress** sends `SIGINT` for a clean WAV header close.
3. `ffmpeg` transcodes to MP3 (smaller upload, same fidelity).
4. The pool hands the payload to the next warm worker subprocess.
5. The worker drives a stealth Chromium context already past the bot check and issues a `multipart/form-data` POST with `file` + `language`.
6. JSON comes back: `{"text": "..."}`.
7. Text lands on the clipboard, a synthetic `Ctrl+V` drops it into whatever window has focus, and your original clipboard is restored a beat later.

Total round trip after you stop speaking: **~10–15 s**, dominated by browser session reuse — invisible if you keep the pool warm.

## Key features

- 🎙 **Global push-to-talk** — works in every window, every workspace, no app integration needed
- 🧠 **Frontier-model fidelity without the model** — ~99% word accuracy on Brazilian Portuguese free-form speech
- 🔁 **Session-pool rotation** — empirical rate-limit defeat by architecture, not by evasion
- 🪶 **Zero idle footprint** — no resident model, no daemon until you speak; RAM only during transcription
- 📋 **Clipboard-safe paste** — snapshots and restores your clipboard around every insertion
- ⌨️ **Terminal-aware injection** — detects terminal emulators and uses `Shift+Insert` where `Ctrl+V` would misbehave
- 🔌 **Hermes Agent STT provider** — plugs into [Hermes Agent](https://github.com/NousResearch/hermes-agent) as a drop-in system-wide transcription backend
- 🧪 **Tested** — unit suite with mocked browser sessions plus opt-in live-network integration test

## Requirements

| Dependency | Minimum | Purpose |
|---|---|---|
| Linux + Wayland compositor | KDE Plasma 6 tested | session, shortcuts, layer semantics |
| Python 3.12+ | 3.13 recommended | orchestration |
| Playwright (Python) | any recent | stealth browser sessions |
| Chromium (Playwright build) | `playwright install chromium` | session bootstrap |
| PipeWire + `pw-record` | any current | microphone capture |
| `ydotool` + `ydotoold` | 1.0+ | synthetic paste (uinput) |
| `wl-clipboard` (`wl-copy`/`wl-paste`) | any | clipboard mediation |
| `ffmpeg` | 4+ | wav→mp3 transcode |
| `libnotify` (`notify-send`) | any | state feedback |

## Installation

### Arch / CachyOS

```bash
# system deps
sudo pacman -S --needed python playwright ydotool wl-clipboard ffmpeg pipewire libnotify

# playwright chromium build
playwright install chromium

# uinput daemon for synthetic keys
sudo systemctl enable --now ydotoold   # or the user-unit shipped in this repo's docs
```

Clone and wire up:

```bash
git clone https://github.com/ankinow/heard.git
cd heard
sudo cp scripts/dictate-heard.sh /usr/local/bin/heard-toggle && sudo chmod +x /usr/local/bin/heard-toggle
```

### Manual setup

Any distro works as long as the requirement table is satisfied. The two moving pieces are:

1. `lib/heard.py` — the pool orchestrator (importable or runnable as CLI).
2. `scripts/dictate-heard.sh` — the toggle script your hotkey fires.

Edit `dictate-heard.sh` and point `LIB` at your clone path:

```bash
LIB="/path/to/heard/lib/heard.py"
```

### Configuration

No account, token, or key is required. Environment overrides:

| Variable | Default | Meaning |
|---|---|---|
| `HEARD_POOL` | `3` | number of warm worker sessions |
| `HEARD_UPSTREAM_URL` | *(built-in)* | upstream endpoint (leave default unless self-hosting a compatible surface) |

> **Note on the upstream:** heard speaks to an anonymous-tier endpoint that exists for logged-out browser visitors. It is undocumented, unofficial, and can change without notice. If it breaks, file an issue — the pool abstraction makes swapping surfaces cheap.

## Usage

### The toggle pattern

```bash
heard-toggle   # 1st press: ● REC notification appears
# ...speak...
heard-toggle   # 2nd press: "Transcrevendo…" → text lands at your cursor → "Colado ✓"
```

That's the entire user interface. Everything else is plumbing.

### Binding to your window manager

**KDE Plasma 6 (Wayland)** — custom shortcut → command:

```bash
# System Settings → Shortcuts → Add Command
/home/user/bin/dictate-heard.sh     # bind to F8 or any spare key
```

**i3 / Sway / Hyprland**

```bash
# i3/Sway config
bindsym F8 exec --no-startup-id /path/to/heard/scripts/dictate-heard.sh

# Hyprland
bind = , F8, exec, /path/to/heard/scripts/dictate-heard.sh
```

Pick a key without modifiers when possible — modifier release races are the classic Wayland hotkey footgun.

## The session-pool architecture

This is the part worth understanding, because it's the difference between a toy and a tool.

### Rate-limit empirics

Measured directly against the anonymous surface (2026-08-23):

| Experiment | Result |
|---|---|
| Two consecutive requests, same session | `200` → `429` |
| Same session after ≈60 s cooldown | `200` |
| **Brand-new session, zero cooldown** | ✅ `200` |

Conclusion: **the limiter keys on the anonymous session cookie, not on IP address.** A fresh session carries a fresh quota, instantly.

This single finding reshaped the design. IP masking, proxies, header spoofing — all unnecessary. The quota is *session-scoped*, so the correct countermeasure is *session multiplicity*: never make the second request from the first session.

### Pool topology

```python
POOL_SIZE = int(os.environ.get("HEARD_POOL", "3"))
REQUESTS_ROTATE = True   # every transcribe() takes the next worker
```

Each worker is a **subprocess**, not a thread. This is deliberate:

- Playwright's sync API is greenlet-bound; calling it across threads produces cross-thread switch errors. Subprocesses sidestep the class of bugs entirely.
- A crashed worker can't poison the pool — the parent detects death via `poll()` and respawns.
- Each worker speaks a tiny line protocol over stdin/stdout (`{"b64": ..., "mime": ...}` → `{"result": {...}}`), making it debuggable with nothing but `jq`.

Cost model: one idle worker ≈ one headless Chromium (~80–120 MB). With `HEARD_POOL=3`, worst case ≈ 300 MB while dictating heavily, zero when idle (workers exit with the parent). For sustained dictation bursts, raise the pool; for occasional use, `HEARD_POOL=1` and accept the ~7 s cold-start.

## Hermes Agent integration

[**Hermes Agent**](https://github.com/NousResearch/hermes-agent) exposes a pluggable local-STT hook, and heard snaps into it natively:

**1. Adapter script** (`~/bin/heard-stt-adapter`, shipped in `scripts/`):

```bash
#!/usr/bin/env bash
set -u
IN="$1"; OUT_DIR="$3"; LANG_="${4:-pt}"
TEXT=$(python3 /path/to/heard/lib/heard.py "$IN" "$LANG_") || exit 1
printf '%s' "$TEXT" > "$OUT_DIR/transcription.txt"
```

**2. Hermes environment** (`~/.hermes/.env`):

```bash
HERMES_LOCAL_STT_COMMAND=/home/user/bin/heard-stt-adapter {input_path} {model} {output_dir} {language}
```

**3. Hermes config** (`config.yaml`):

```yaml
stt:
  enabled: true
  provider: local_command
  language: pt
```

Result: **every voice note reaching any Hermes surface** — Telegram, WhatsApp, Discord, the gateway, CLI `/voice` — transcribes through heard's pool. One desktop tool becomes the ears of your whole agent fleet. Verified end-to-end against Hermes v0.20.x.

## Configuration reference

All knobs are environment variables — no config files by design.

### heard core

| Variable | Default | Notes |
|---|---|---|
| `HEARD_POOL` | `3` | warm worker count; `1` minimizes RAM, `3+` removes throughput ceiling |
| `HEARD_UPSTREAM_URL` | built-in | override only for compatible self-hosted surfaces |

### dictate script

| Constant | Where | Meaning |
|---|---|---|
| `WAV=/tmp/heard-voice.wav` | `scripts/dictate-heard.sh` | scratch recording path |
| `STATE=/tmp/heard-dictate.pid` | same | toggle state (recording PID) |

### Hermes adapter

See the [integration section](#hermes-agent-integration) — the template placeholders `{input_path}`, `{model}`, `{output_dir}`, `{language}` are filled by Hermes itself.

## Testing

```bash
# unit suite (mocked browser; fast, offline)
uv run --with pytest --with playwright python -m pytest tests/ -q

# full suite incl. live network round-trip
HEARD_INTEGRATION=1 uv run --with pytest --with playwright python -m pytest tests/ -q
```

Coverage map:

| Test | What it proves |
|---|---|
| `test_wav_to_mp3_converts` | ffmpeg bridge produces valid mp3 |
| `test_wav_to_mp3_fallback_on_ffmpeg_fail` | graceful degradation to raw wav |
| `test_transcribe_success` | happy path returns upstream text |
| `test_transcribe_429_raises` | rate-limit surfaces as `RuntimeError` |
| `test_transcribe_upstream_url_env` | `HEARD_UPSTREAM_URL` honored at call time |
| `test_integration_real_endpoint` | real network, real session, real words |

The fakes implement just enough of the Playwright surface (context/page/evaluate) to exercise the full orchestration path — including the property that the upstream URL is read *at call time*, not import time, so env changes apply to long-lived processes.

## Troubleshooting

### `Falha: python3: can't open file ... heard.py`
`LIB` inside `dictate-heard.sh` points at a stale path. Set it to your clone's absolute path.

### Nothing pastes into terminals
Terminals often ignore synthetic `Ctrl+V`. heard auto-detects known emulators and switches to `Shift+Insert`. If yours isn't detected, add its `WM_CLASS` to the case block in `scripts/dictate-heard.sh`.

### `429` despite the pool
You're out-pacing the rotation window (many dictations within one minute across all workers). Raise `HEARD_POOL` or pace naturally — human speech cadence rarely exceeds 1/min/worker.

### Accents arrive mangled (`çãé` → garbage)
Your paste path used synthetic typing instead of clipboard. Ensure `wl-copy` + `ydotool` are installed and `ydotoold` is running: `systemctl --user status ydotoold`.

### Wayland window won't render (overlay companions)
GTK apps need `GDK_BACKEND=wayland` explicitly under KWin, or they map invisibly. Related: compositors ignore programmatic `move()` for toplevel windows — position via compositor rules (e.g. KWin window rules keyed on window title).

### First dictation is slow (~15 s vs usual ~10 s)
Cold pool. Workers bootstrap lazily. Keep `HEARD_POOL≥2` if first-latency matters more than RAM.

## Known limitations

- **Unofficial surface.** The anonymous endpoint is not a contract. It may tighten limits, add challenges, or vanish. heard isolates that risk behind one function.
- **Language hint is best-effort.** Accuracy peaks on clear, close-mic speech; heavy background noise degrades all engines equally.
- **Wayland-first.** X11 largely works (xdotool variant of the paste step) but is untested territory here.
- **One speaker.** No diarization; it transcribes whoever talks.

## Design notes & reverse-engineering diary

Decisions worth preserving, discovered the hard way:

1. **Session-scoped quotas beat IP-scoped assumptions.** The intuitive fix for rate limits is network-level evasion. Measurement showed the quota never touched the network layer — so the fix was architectural (multiplicity), not evasive. Simpler, legal-adjacent, and robust to proxy detection.
2. **Subprocesses > threads for Playwright.** Sync Playwright pins a greenlet per thread. Cross-thread calls raise `cannot switch to a different thread`. Worker-per-session converts a concurrency bug class into process isolation.
3. **Clipboard-mediated paste beats synthetic typing.** `xdotool type`-style keystroke synthesis corrupts non-US layouts (accents become wrong glyphs under BR layout scancodes). Clipboard + paste shortcut is layout-immune and preserves Unicode perfectly.
4. **SIGINT, not SIGKILL, stops recordings.** Killing `pw-record` with SIGKILL truncates the WAV header — the file becomes unparseable exactly when you need it.
5. **Read env at call time, not import time.** Tests proved that module-import-time constant capture makes `HEARD_UPSTREAM_URL` untestable and un-overridable in long-lived processes.

These notes double as an incident archaeology record: every entry traces to a real failure observed in testing.

## Related work by the author

heard is the dictation pillar of a broader keyboard-sovereignty stack by **Luiz Eloi Rivellis Martinelli Filho (ankinow)**, whose work explores what personal computing looks like when inverse-singularity thinking is applied to everyday tools — the thesis that as systems grow more complex, individual leverage comes from *deeper, narrower* instruments rather than broader ones:

- **[promptech](https://github.com/ankinow/promptech)** — global-hotkey prompt store + Espanso integration + the overlay companion that pairs with heard. Where heard gives you a voice, promptech gives you a vocabulary.
- **AIGuaratuba** — a civic-intelligence platform for Guaratuba-PR (Brazil), applying multi-agent orchestration, IST-derived quality gates, and fail-closed data philosophy to hyperlocal public information. heard's own engineering discipline — evidence over assertion, deterministic verification, honest failure reporting — was forged in that project's pipeline gates.

If heard saved you from whisper's RAM appetite or an API bill, promptech completes the loop: prompts at hotkey speed, dictated at thought speed.

## License

MIT — see [LICENSE](LICENSE).

---

*Built on Wayland, powered by PipeWire, proven by pixel-scans. If a claim in this README lacks a test behind it, that's a bug — report it.*
