"""Guard -- VALIDATE · ARBITRATE · GUARD (L4 와 L5 사이, baseline BD-07 · BD-20 · BD-24). 지금은 **shadow** 뿐이다.

    validate(intent, dc, model)                -> ValidationResult   A0–A4: 꼴 · 자기 DC 안의 근거
    guard(intent, dc, state, model)            -> GuardResult        D · A5–A8: 지금 상태 기준의 허가. 닫는 쪽으로만
    evaluate(intent, dc, state, model)         -> (ValidationResult, GuardResult)
    command_material(result, intent)           -> ActionCommand 재료(ALLOW · SAFE_ACTION)

Policy · CR · MS 를 import 하지 않는다. 의존: action 계약(`action-contract/1`, 커밋 고정) · 표준 라이브러리.
"""
from .command import build_command, command_material
from .forms import (ALLOW, DENY, ENFORCE, SAFE_ACTION, SHADOW, FormError, GuardResult, ValidationResult)
from .rules import evaluate, guard, repeat_key, validate
from .views import ActionSpec, DCView, Entity, GuardModel, Prop, StateView, ViewError

__all__ = ["ALLOW", "DENY", "SAFE_ACTION", "SHADOW", "ENFORCE", "FormError", "GuardResult", "ValidationResult",
           "evaluate", "guard", "validate", "repeat_key", "command_material", "build_command",
           "ActionSpec", "DCView", "Entity", "GuardModel", "Prop", "StateView", "ViewError"]
