"""Import-path shim so tests can `import` the src/ modules directly, and
locate the frozen fixtures, without installing the project as a package."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
FIXTURES = ROOT / "fixtures"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
