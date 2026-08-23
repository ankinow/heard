#!/usr/bin/env bash
# heard — ditado toggle (F8): grava mic -> transcribe anônimo -> cola na janela focada
set -u
STATE=/tmp/heard-dictate.pid
WAV=/tmp/heard-voice.wav
LIB="$(dirname "$(readlink -f "$0")")/../lib/heard.py"

paste() {
  local old; old=$(wl-paste 2>/dev/null || true)
  printf '%s' "$1" | wl-copy; sleep 0.15
  if command -v ydotool >/dev/null && pgrep -x ydotoold >/dev/null; then
    ydotool key 29:1 47:1 47:0 29:0
  elif command -v wtype >/dev/null; then wtype -M ctrl -k v -m ctrl
  else notify-send -u critical "heard" "sem ydotoold/wtype"; exit 1; fi
  ( sleep 1.5; printf '%s' "$old" | wl-copy ) &
}

if [[ -f $STATE ]]; then
  PID=$(cat "$STATE"); kill -INT "$PID" 2>/dev/null && sleep 0.4; kill -TERM "$PID" 2>/dev/null
  rm -f "$STATE"
  notify-send -t 3000 "heard" "Transcrevendo (~10s)…"
  TEXT=$(python3 "$LIB" "$WAV" pt 2>/tmp/heard-err.log) || {
    notify-send -u critical "heard" "Falha: $(tail -1 /tmp/heard-err.log)"; exit 1; }
  [[ -z ${TEXT// } ]] && { notify-send -u critical "heard" "texto vazio"; exit 1; }
  paste "$TEXT"
  notify-send -t 1500 "heard" "Colado ✓"
else
  rm -f "$WAV"
  pw-record --channels=1 --rate=16000 "$WAV" &
  echo $! > "$STATE"
  notify-send -t 2500 "heard ● REC" "F8 de novo para parar"
fi
