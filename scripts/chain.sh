#!/bin/bash
# Record 19 June 2023 and 20 May 2026 with latency, build both pages. Logs to runs/chain.log.
cd "$(dirname "$0")/.." || exit 1
export PATH="$HOME/.local/bin:$PATH"
echo "$(date +%H:%M:%S) start"
uv run python scripts/record_sitting.py data/raw/steno/2023-06-19.json runs/chair/2023-06-19.json 200 2>&1 | grep -E "done:|Traceback|tone: |stimuli"
echo "$(date +%H:%M:%S) 19 June recorded"
uv run python scripts/build_sitting.py data/raw/steno/2023-06-19.json runs/chair/2023-06-19.json runs/page/chair-2023-06-19.html 2>&1 | grep -E "bytes|Traceback|unscored"
echo "BUILT_DAY2"
uv run python scripts/record_sitting.py data/raw/meta/steno_verbatims_20260520.json runs/chair/2026-05-20.json 2>&1 | grep -E "done:|Traceback"
echo "$(date +%H:%M:%S) 20 May re-recorded"
uv run python scripts/build_sitting.py data/raw/meta/steno_verbatims_20260520.json runs/chair/2026-05-20.json runs/page/chair.html 2>&1 | grep -E "bytes|Traceback"
echo "REBUILT_BOTH"
