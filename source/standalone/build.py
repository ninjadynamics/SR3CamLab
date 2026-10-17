"""Build and test with the setup GCC; see BUILD.md."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_build import main
if __name__ == '__main__':
    main()
