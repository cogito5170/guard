"""(옮김 흔적, CMD-G5) 술어는 action 의 한 벌이다(BD-108). 여기에는 구현이 없다 -- 다시 내보내기만 한다.

guard 코드는 이 모듈을 쓰지 않는다(`from action import predicate`). action 의 대조 시험(`tests/test_predicate.py` 의
SameAsGuard)이 옆 저장소의 `guard.predicate` 를 읽으므로 남겨 둔다. 그 시험이 걷히면 지운다.
"""
from action.predicate import OPS, _rhs, check, holds, props_of  # noqa: F401
