"""Command line entry point. Subcommands land as their stages are built (see SPEC.md)."""

import argparse

STAGES = {
    "harvest": "Stage 0 — fetch Riigikogu votes and bills into the cache",
    "pretest": "Stage 0 — offline tests T1-T5; decides whether the question is answerable",
    "score": "Stage 1 — LLM topic scores for cached bills",
    "run": "Stage 3 — simulate Kärbes's vote on every bill, from cache",
    "sync": "Stage 5 — fetch only sittings newer than the cache watermark",
}


def main() -> int:
    parser = argparse.ArgumentParser(prog="karbes", description=__doc__)
    sub = parser.add_subparsers(dest="command")
    for name, help_text in STAGES.items():
        sub.add_parser(name, help=help_text)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 0

    raise SystemExit(f"'{args.command}' is not implemented yet: {STAGES[args.command]}")


if __name__ == "__main__":
    raise SystemExit(main())
