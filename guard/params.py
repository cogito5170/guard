"""(옮김 흔적, CMD-G5) 인자 검사는 action 의 한 벌이다(BD-108). 여기에는 구현이 없다 -- 다시 내보내기만 한다.

guard 코드는 이 모듈을 쓰지 않는다(`from action.params import check_args`). action 의 대조 시험(Params.test_same_as_guard)이
옆 저장소의 `guard.params` 를 읽으므로 남겨 둔다. 그 시험이 걷히면 지운다.
"""
from action.params import TYPES, check_args  # noqa: F401
