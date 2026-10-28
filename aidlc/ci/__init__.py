"""CI workflows and CODEOWNERS for an adopting repository.

Workflow files are templates with one placeholder, the install command
(GitHub's own `${{ }}` expressions pass through untouched).
"""

from pathlib import Path

from aidlc import __version__
from aidlc.reviewers import CODEOWNERS_PATH, codeowners

__all__ = ["CODEOWNERS_PATH", "DEFAULT_INSTALL", "codeowners", "workflows"]

HERE = Path(__file__).parent
WORKFLOWS_DIR = ".github/workflows"
DEFAULT_INSTALL = f"pip install aidlc-kit=={__version__}"


def workflows(install: str = DEFAULT_INSTALL) -> dict[str, str]:
    return {
        f"{WORKFLOWS_DIR}/{path.name}": path.read_text(encoding="utf-8").replace("@@INSTALL@@", install)
        for path in sorted(HERE.glob("aidlc-*.yml"))
    }
