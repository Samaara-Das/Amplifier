"""pytest configuration for UAT Task #14 tests.

Adds --campaign-id CLI option. Falls back to reading data/uat/last_campaign_id.txt
when the option is not provided.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

ID_FILE = ROOT / "data" / "uat" / "last_campaign_id.txt"


def pytest_addoption(parser):
    parser.addoption(
        "--campaign-id",
        action="store",
        type=int,
        default=None,
        help="Campaign ID to use in UAT tests. Defaults to contents of data/uat/last_campaign_id.txt",
    )


def pytest_configure(config):
    pass


def get_campaign_id(config) -> int:
    cid = config.getoption("--campaign-id", default=None)
    if cid is not None:
        return cid
    if ID_FILE.exists():
        try:
            return int(ID_FILE.read_text().strip())
        except (ValueError, OSError):
            pass
    raise RuntimeError(
        "No campaign ID available. Either pass --campaign-id or run seed_campaign.py first "
        "to populate data/uat/last_campaign_id.txt"
    )
