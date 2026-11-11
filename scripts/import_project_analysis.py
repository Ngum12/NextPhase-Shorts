"""Import a prepared English transcript into one allowlisted app project."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api'))

if __name__ == '__main__':
    from app.project_analysis import main
    raise SystemExit(main())
