"""ALLOW · SAFE_ACTION 뒤의 ActionCommand(action-contract/1) 재료.

Guard 는 명령을 **배차하지 않는다**. 재료(intent_id · action · target · args)만 낸다. `decision_ref`(MS DecisionRecord id) ·
`issued_at` · `deadline` 은 배차하는 쪽(런타임)이 안다 -- `build_command` 로 채운다. shadow 에서는 런타임이 자기 중재
결정대로 진행하므로, 이 재료는 기록 · 대조용이다.
"""
from __future__ import annotations

from action.forms import ActionCommand, ActionIntent

from .forms import ALLOW, SAFE_ACTION, GuardResult


def command_material(result: GuardResult, intent: ActionIntent) -> dict:
    if result.intent_id != intent.id:
        raise ValueError(f"결과({result.intent_id}) 가 이 의도({intent.id}) 의 것이 아니다")
    if result.verdict == ALLOW:
        return {"intent_id": intent.id, "action": intent.action, "target": intent.target, "args": dict(intent.args)}
    if result.verdict == SAFE_ACTION:          # 갈아 끼운 행동은 목적 단위의 기본 결정이다 -- 겨냥 · 인자를 물려받지 않는다
        return {"intent_id": intent.id, "action": result.safe_action, "target": None, "args": {}}
    raise ValueError(f"{result.verdict} 에는 명령이 없다")


def build_command(material: dict, decision_ref: str, issued_at: float, deadline: "float | None" = None) -> ActionCommand:
    return ActionCommand(intent_id=material["intent_id"], decision_ref=decision_ref, action=material["action"],
                         target=material["target"], args=material["args"], issued_at=issued_at, deadline=deadline)
