#!/usr/bin/env bash
# External-terminal launcher (tmux) — never tie the long Flux/Wan render to Cursor.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
SESSION="us-stoop-almost-10s"
LOG="$ROOT/temp/us_stoop_almost_10s/run.log"
mkdir -p "$ROOT/temp/us_stoop_almost_10s" "$ROOT/final_outputs"

PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="${PYTHON:-python3}"
fi

TMUX_CONF="/exec-daemon/tmux.portal.conf"
TMUX=(tmux)
if [[ -f "$TMUX_CONF" ]]; then
  TMUX=(tmux -f "$TMUX_CONF")
fi

echo "========================================"
echo " Brooklyn Stoop — The Almost (10s)"
echo " Quality OS: Flux 24 + Wan two-pass 14"
echo " Log: $LOG"
echo " Out: $ROOT/final_outputs/US_Brooklyn_Stoop_Almost_10s.mp4"
echo " tmux session: $SESSION"
echo "========================================"

"${TMUX[@]}" has-session -t "=$SESSION" 2>/dev/null || \
  "${TMUX[@]}" new-session -d -s "$SESSION" -c "$ROOT" -- "${SHELL:-bash}" -l

# Clear any leftover command, then start the render with logging.
"${TMUX[@]}" send-keys -t "$SESSION:0.0" C-c 2>/dev/null || true
"${TMUX[@]}" send-keys -t "$SESSION:0.0" \
  "cd '$ROOT' && $PY -u scripts/render_us_stoop_almost_10s.py 2>&1 | tee -a '$LOG'; echo EXIT \$? | tee -a '$LOG'" \
  C-m

echo "Launched in tmux session '$SESSION'."
echo "Attach: tmux attach -t $SESSION"
echo "Log: $LOG"
