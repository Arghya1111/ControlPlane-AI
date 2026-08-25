"""ControlPlane.ai backend package."""
import sys
from pathlib import Path

# Ensure backend root is present in sys.path so 'app' and 'backend.app' modules resolve cleanly
_backend_dir = str(Path(__file__).resolve().parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
