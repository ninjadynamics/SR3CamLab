"""Build the raylib companion from source with the setup GCC."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_build import main
if __name__ == '__main__':
    main(default_target='companion')
