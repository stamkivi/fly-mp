import subprocess
import sys


def test_cli_lists_stages_in_order():
    """Stage order is a gate, not a preference: nothing is scored before the corpus is cached."""
    out = subprocess.run(
        [sys.executable, "-m", "karbes.cli", "--help"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert out.index("harvest") < out.index("pretest") < out.index("score")
