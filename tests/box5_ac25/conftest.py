import sys
from pathlib import Path

# scripts/ci 를 import 경로에 추가(ac25 패키지 로드)
_CI = Path(__file__).resolve().parents[2] / "scripts" / "ci"
if str(_CI) not in sys.path:
    sys.path.insert(0, str(_CI))
