"""Command line entry point. Subcommands land as their stages are built (see SPEC.md)."""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

DATA = Path("data/raw")


def _harvest(args: argparse.Namespace) -> int:
    from karbes.riigikogu.corpus import harvest
    from karbes.riigikogu.model import TERM_START

    start = date.fromisoformat(args.start) if args.start else TERM_START
    stats = harvest(DATA, start=start, refresh_last_range=args.refresh)
    print(f"\nsittings              {stats['sittings']:>6,}")
    print(f"substantive votings   {stats['substantive_votings']:>6,}")
    print(f"unique bills          {stats['unique_bills']:>6,}")
    print(f"requests made         {stats['requests_made']:>6,}")
    print(f"cache hits / misses   {stats['cache_hits']:>6,} / {stats['cache_misses']:,}")
    if stats["gaps"]:
        print(f"gaps                  {len(stats['gaps']):>6,}  (see data/raw/gaps.json)")
    return 0


def _pretest(args: argparse.Namespace) -> int:
    from karbes.analysis.pretests import run_pretests

    return run_pretests(DATA, verbose=not args.quiet)


def _score(args: argparse.Namespace) -> int:
    from karbes.analysis.pilot import run_pilot

    return run_pilot(DATA, force=args.force, verbose=not args.quiet, full=args.full)


MALECNS = Path("data/malecns")
RUNS = Path("runs")


def _load_engine():
    """Populations and the published LIF engine pack, or a clear instruction."""
    from karbes import engine as E
    from karbes.graph import populations as P

    try:
        engine = E.load()
    except Exception as exc:  # pack missing, or mlx not installed
        raise SystemExit(
            f"cannot load the engine pack ({exc}).\n"
            "Install the engine and build the MaleCNS pack:\n"
            "  uv pip install -e ../drosophila-brain-mlx\n"
            "  cd ../drosophila-brain-mlx && python -m lif.compile_pack_malecns"
        ) from exc
    return P.load(MALECNS), engine


def _calibrate(args: argparse.Namespace) -> int:
    import json

    from karbes import replay

    pops, engine = _load_engine()
    result = replay.calibrate(engine, pops, seeds=args.seeds)
    RUNS.mkdir(exist_ok=True)
    (RUNS / "calibration.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"\nbaseline bias (blank bill)  {result['baseline_bias']:>+8.4f}")
    print(f"noise (blank-bill SD)       {result['noise_sd']:>8.4f}")
    print(f"signal (mean channel span)  {result['signal']:>8.4f}")
    print(f"SNR                         {result['snr']:>8.3f}")
    print(f"dead band                   {result['dead_band']:>8.4f}")
    print(f"network rate                {result['network_hz']:>8.3f} Hz")
    resolved = result["channels_resolved_above_noise"]
    print(
        f"\nchannels separable from the noise: "
        f"{len(resolved)} of {len(result['sweep'])}"
        + (f"  ({', '.join(resolved)})" if resolved else "")
    )
    print(f"\nwritten to {RUNS / 'calibration.json'}")
    return 0


def _replay(args: argparse.Namespace) -> int:
    import json

    from karbes import atlas as A
    from karbes import replay
    from karbes.analysis import idealpoint, votematrix
    from karbes.riigikogu.corpus import load_bills, load_votes
    from karbes.score.jev import JevScorer

    pops, engine = _load_engine()
    soma = A.load(MALECNS)
    if soma is None:
        soma = A.build(MALECNS)
        A.save(soma, MALECNS)

    votes = load_votes(DATA)
    bills = load_bills(DATA)
    log = logging.getLogger("karbes.cli")
    log.info("corpus: %d votings on %d bills", len(votes), len(bills))

    with JevScorer(DATA) as scorer:
        if args.bill:
            wanted = [v for v in votes if v.draft_uuid == args.bill]
            if not wanted:
                raise SystemExit(f"no substantive voting on bill {args.bill}")
            scores = {args.bill: scorer.score(bills[args.bill])}
        else:
            # Only bills with text can be scored, and an unscorable bill is excluded
            # rather than defaulted to zeros.
            scores = {
                uuid: scorer.score(bills[uuid])
                for uuid in {v.draft_uuid for v in votes}
                if uuid in bills and bills[uuid].has_text
            }
        scores = {k: v for k, v in scores.items() if v is not None}
        if scorer.calls:
            log.info("scored %d bills live, $%.4f", scorer.calls, scorer.cost_usd)

    bill, vote = (
        (
            bills[args.bill],
            max((v for v in votes if v.draft_uuid == args.bill), key=lambda v: v.when),
        )
        if args.bill
        else replay.pick_bill(bills, votes, scores)
    )

    vm = votematrix.build(votes)
    space = idealpoint.fit(vm, dims=2)

    calibration = RUNS / "calibration.json"
    if not calibration.exists():
        raise SystemExit(f"no {calibration}; run `karbes calibrate` first")
    cal = json.loads(calibration.read_text(encoding="utf-8"))

    bundle = replay.build(
        replay.Inputs(
            bill=bill,
            vote=vote,
            scored=scores[bill.uuid],
            engine=engine,
            pops=pops,
            atlas=soma,
            space=space,
            vm=vm,
            bias=cal["baseline_bias"],
            dead_band=cal["dead_band"],
            seed=args.seed,
            seeds=args.seeds,
        )
    )
    doc, blob = bundle.write(RUNS / "replay")

    from karbes import page as P

    html = P.write(
        RUNS / "page" / "index.html",
        P.build(bundle.doc, bundle.raster, soma, json.loads(calibration.read_text("utf-8"))),
    )

    v = bundle.doc["verdict"]
    print(f"\nbill      {bill.title[:72]}")
    print(f"chamber   {'advances' if v['chamber_advances'] else 'rejects'} the bill")
    print(
        f"Karbes    {v['code']}  (turn {bundle.doc['race']['turn']:+.4f}, "
        f"dead band {cal['dead_band']:.4f})"
    )
    print(f"agrees    {v['agrees_with_chamber']}")
    print(f"\n{doc} ({doc.stat().st_size:,} B)")
    print(f"{blob} ({blob.stat().st_size:,} B)")
    print(f"{html} ({html.stat().st_size:,} B)")
    return 0


def _unimplemented(stage: str):
    def run(args: argparse.Namespace) -> int:
        raise SystemExit(f"'{stage}' is not implemented yet")

    return run


def main() -> int:
    parser = argparse.ArgumentParser(prog="karbes", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("harvest", help="Stage 0 — fetch votes and bills into the cache")
    p.add_argument("--start", help="ISO date; defaults to the start of the XV Riigikogu")
    p.add_argument(
        "--refresh",
        action="store_true",
        help="refetch the current year's voting list (it is still accruing)",
    )
    p.set_defaults(func=_harvest)

    p = sub.add_parser("pretest", help="Stage 0 — offline tests T1-T5; gates everything after")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=_pretest)

    p = sub.add_parser("score", help="Stage 1 — rubric pilot (P1-P5); gates the full LLM pass")
    p.add_argument("--force", action="store_true", help="run even if the stage 0 gate failed")
    p.add_argument(
        "--full", action="store_true", help="score every bill with text, for statistical power"
    )
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=_score)

    p = sub.add_parser("calibrate", help="Stage 2b — measure the dead band and the SNR")
    p.add_argument("--seeds", type=int, default=12, help="input phases averaged per point")
    p.set_defaults(func=_calibrate)

    p = sub.add_parser("replay", help="Stage 2b — build one bill's replay bundle")
    p.add_argument("--bill", help="draft UUID; defaults to the pre-registered pick")
    p.add_argument("--seed", type=int, default=0, help="input phase; the fly wavers with it")
    p.add_argument(
        "--seeds", type=int, default=8, help="input phases to re-run, to measure the wavering"
    )
    p.set_defaults(func=_replay)

    for name, help_text in [
        ("run", "Stage 3 — simulate Kärbes's vote on every bill, from cache"),
        ("sync", "Stage 5 — fetch only sittings newer than the cache watermark"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.set_defaults(func=_unimplemented(name))

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    if args.command is None:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
