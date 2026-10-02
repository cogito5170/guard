"""시험이 action 계약을 찾는 곳: 설치된 `action-contract`(pyproject 의 커밋 고정) → ACTION_REPO → 옆 디렉터리."""
import os
import pathlib
import sys

try:
    import action  # noqa: F401
except ImportError:
    here = pathlib.Path(__file__).resolve().parent.parent
    for p in filter(None, [os.environ.get("ACTION_REPO"), here.parent / "action", here.parent / "cogito5170" / "action"]):
        if (pathlib.Path(p) / "action" / "forms.py").exists():
            sys.path.insert(0, str(p))
            break
