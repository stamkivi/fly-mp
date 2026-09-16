from karbes.cli import STAGES


def test_harvest_precedes_scoring():
    """Stage order is a gate, not a preference: nothing is scored before the corpus is cached."""
    stages = list(STAGES)
    assert stages.index("harvest") < stages.index("pretest") < stages.index("score")
