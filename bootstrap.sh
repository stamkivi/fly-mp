#!/bin/bash
# Unattended data acquisition. Everything here is cached and resumable.
set -u
cd ~/git/fly-mp
log() { echo "[$(date +%H:%M:%S)] $*"; }

log "disk before: $(df -h . | tail -1 | awk "{print \$4}") free"

log "=== 1/4 Riigikogu harvest (~80 min, rate limited) ==="
uv run karbes harvest --refresh 2>&1 | grep -vE "HTTP Request" | tail -20

log "=== 2/4 MaleCNS connectome (~1.06 GB) ==="
bash scripts_fetch.sh

log "=== 3/4 compile CSR ==="
uv run python -c "
from pathlib import Path
from karbes.graph import populations as P, sign as S, load as L, pin
root=Path(\"data/malecns\")
for f in (P.ANNOTATIONS, S.NEUROTRANSMITTERS, L.WEIGHTS): pin.record(root, f, root/f)
p=P.load(root); s,_=S.signs(root, p.retained)
g=L.compile_graph(root, p.retained, s); L.save(g, root)
print(f\"graph: {g.n:,} neurons {g.nnz:,} edges\")
" 2>&1 | grep -vE "rows, .* edges kept" | tail -5

log "=== 4/4 score bills with Jev (~30 s) ==="
uv run python -c "
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from karbes.riigikogu.corpus import load_bills
from karbes.score.jev import JevScorer
bills=[b for b in load_bills(Path(\"data/raw\")).values() if b.has_text]
with JevScorer(Path(\"data/raw\")) as s:
    with ThreadPoolExecutor(max_workers=8) as pool: r=list(pool.map(s.score, bills))
    print(f\"scored {sum(1 for x in r if x)}/{len(bills)} cost \${s.cost_usd:.4f}\")
" 2>&1 | tail -3

log "disk after: $(df -h . | tail -1 | awk "{print \$4}") free"
log "=== BOOTSTRAP COMPLETE ==="
uv run karbes pretest 2>&1 | tail -6
