#!/bin/bash
# Record both sittings with latency, then build every page. Logs to runs/chain.log.
cd "$(dirname "$0")/.." || exit 1
export PATH="$HOME/.local/bin:$PATH"
echo "$(date +%H:%M:%S) start"
uv run python scripts/record_sitting.py data/raw/steno/2023-06-19.json runs/chair/2023-06-19.json 200 2>&1 | grep -E "done:|Traceback|tone: |stimuli"
echo "$(date +%H:%M:%S) 19 June recorded"
uv run python scripts/record_sitting.py data/raw/meta/steno_verbatims_20260520.json runs/chair/2026-05-20.json 2>&1 | grep -E "done:|Traceback"
echo "$(date +%H:%M:%S) 20 May recorded"
uv run python scripts/build_site.py 2>&1 | grep -E "bytes|Traceback|unscored"
echo "BUILT_ALL"
