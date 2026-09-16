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

    return run_pilot(DATA, force=args.force, verbose=not args.quiet)


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
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=_score)

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
