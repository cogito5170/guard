"""VALIDATE(A0–A4) · GUARD(D · A5–A8) -- 둘 다 순수 함수다. 같은 입력이면 같은 결과, 숨은 상태 없음.

규칙의 뜻은 MS `ms/arbiter.py` 와 같다(BD-24 배분). 다른 점:
- **지금** 상태를 입력(StateView)으로 받는다. MS 는 State Manager 를 직접 읽는다.
- 되풀이(A8)의 기억은 Guard 안에 두지 않는다. 호출자가 ALLOW 뒤 `repeat_key` 를 StateView.allowed 에 더한다.
- GUARD 는 걸린 규칙을 **모두** 본다(제약은 논리곱, DATA_FLOW §6.4). `rule` 은 MS 와 같은 순서에서 처음 걸린 것이고,
  `reasons` 에 걸린 것 전부가 있다. MS 는 처음 걸린 것에서 멈춘다.
- D(새): DC 가 불완전하거나, 필수 키 · 의도가 쓴 키 가운데 낡은 것이 있으면 위험 등급 행동을 막는다(DATA_FLOW §6.5 · BD-103). 목적의 기본 행동이 있으면
  SAFE_ACTION 으로 갈아 끼우고, 없거나 실행기 행동(GuardModel 의 ActionSpec)이 아니면 DENY 다(BD-104).

닫는 쪽으로만: `evaluate` 는 VALIDATE 가 막은 의도를 GUARD 로 넘기지 않는다. GUARD 가 ALLOW 를 내는 길은 걸린 규칙이
하나도 없을 때 하나뿐이다. 예외는 DENY(rule E)다.

모드: 판정은 모드와 무관하다. shadow 는 판정을 기록만 하고 런타임이 하던 대로 진행한다. enforce 는 OQ-17(안전 동작의
전순서 값)이 정해지기 전에는 켜지 않는다 -- `guard(..., mode="enforce")` 는 거절한다.
"""
from __future__ import annotations

import json

from action.canonical import digest
from action.forms import ActionIntent, ContractError

from . import predicate
from .forms import ALLOW, DENY, PASS, SAFE_ACTION, SHADOW, GuardResult, ValidationResult
from .params import check_args
from .views import DCView, GuardModel, StateView

GRANT_RISKS = ("external", "irreversible")          # A7: 허가가 있어야 하는 위험 등급(MS 와 같다)
NOT_INTENTS = ("none", "retrieve")                  # BD-97: "할 것 없음" · CR 안의 꺼냄은 의도가 되지 않는다
GUARD_ORDER = ("D", "A5", "A6", "A7", "A8")         # rule 로 고르는 순서. A5–A8 은 MS 의 순서 그대로


def _intent_id(intent) -> str:
    """결과에 적을 intent_id. 꼴이 맞지 않는 의도는 받은 것 그대로의 해시로 적는다(믿을 수 있는 id 가 없으므로)."""
    if isinstance(intent, ActionIntent):
        return intent.id
    try:
        return f"int-{digest(intent)}"
    except (ValueError, TypeError):
        return f"int-{digest(repr(intent))}"


def _as_intent(intent) -> "tuple[ActionIntent | None, list]":
    if isinstance(intent, ActionIntent):
        return intent, []
    if isinstance(intent, dict):
        try:
            return ActionIntent.from_dict(intent), []
        except ContractError as e:
            return None, e.errors
    return None, [f"ActionIntent 가 아니다 ({type(intent).__name__})"]


def repeat_key(intent: ActionIntent, version: int) -> str:
    """A8 의 열쇠: (행동 · 대상 · 인자, 대상의 판). MS `Proposal.key()` 와 같은 글. intent_id 는 쓰지 않는다 --
    거기에는 rationale 이 들어 있어 까닭만 바꾼 되풀이를 놓친다(action PC19.md P3)."""
    k = json.dumps([intent.action, intent.target, intent.args], sort_keys=True, ensure_ascii=False)
    return f"{k}@{version}"


# ── VALIDATE ────────────────────────────────────────────────────────────────

def validate(intent, dc: DCView, model: GuardModel) -> ValidationResult:
    """A0–A4: 의도가 꼴이 맞고 **자기 DC 안에서** 근거가 있나. 지금 상태는 보지 않는다."""
    iid = _intent_id(intent)
    try:
        rule, reasons = _validate(intent, dc, model)
    except Exception as e:                                   # 닫힌 쪽으로
        rule, reasons = "E", [f"Validate 예외: {type(e).__name__}: {e}"]
    return ValidationResult(iid, rule == PASS, rule, reasons)


def _validate(intent, dc: DCView, model: GuardModel):
    it, errs = _as_intent(intent)
    if it is None:
        return "A0", errs
    if it.dc_id != dc.dc_id:
        return "A0", [f"의도가 본 DC({it.dc_id}) 가 이 DC({dc.dc_id}) 가 아니다"]
    if it.action in NOT_INTENTS:
        return "A0", [f"{it.action!r} 는 행동 의도가 아니다(BD-97)"]
    if it.action not in dc.offers:
        return "A1", [f"행동 {it.action} 는 이 문맥에서 제안되지 않았다"]
    spec = model.specs.get(it.action)
    if spec is None:
        return "A1", [f"행동 {it.action} 의 ActionSpec 이 Model 에 없다"]
    targets = dc.offers[it.action]
    if it.target is None:
        if None not in targets:
            return "A2", [f"{it.action} 에 겨냥이 없다"]
    else:
        if it.target not in dc.seen:
            how = dc.decisions.get(it.target)
            if how in ("SUMMARIZE", "RETRIEVE", "DEFER"):
                h = next((k for k, ids in dc.handles.items() if it.target in ids), "?")
                return "A2", [f"{it.target} 는 요약 · 손잡이로만 봤다 -- retrieve {h} 먼저"]
            if how == "DROP":
                return "A2", [f"{it.target} 는 맥락 정책이 뺐다(DROP) -- 결정이 본 적 없다"]
            return "A2", [f"{it.target} 는 결정이 본 적 없는 실체다"]
        if it.target not in targets:
            return "A3", [f"{it.target} 는 {it.action} 의 대상이 아니다"]
    bad = check_args(spec.params, it.args)
    if bad:
        return "A4", bad
    return PASS, [f"{it.action} -> {it.target}"]


def stale_in_scope(it: ActionIntent, dc: DCView) -> list:
    """D 가 보는 낡은 키(BD-103): 필수 키 ∪ 의도가 쓴 키. `query:<이름>` 은 그 질의의 행 속성 전부(`"<이름>/…"`).
    결정이 쓰지도 않고 필수도 아닌 키가 낡은 것은 그 행동의 근거가 아니다. `allow_stale` 로 보인 값이라도 의도가 썼으면 건다."""
    used = set(it.used_keys)
    queries = {k[len("query:"):] for k in used if k.startswith("query:")}
    req = set(dc.required_keys)
    return sorted(k for k in dc.stale_keys
                  if k in req or k in used or ("/" in k and k.split("/", 1)[0] in queries))


# ── GUARD ──────────────────────────────────────────────────────────────────

def guard(intent: ActionIntent, dc: DCView, state: StateView, model: GuardModel, mode: str = SHADOW) -> GuardResult:
    """D · A5–A8: 고른 의도를 **지금** 실행해도 되나. VALIDATE 를 지난 의도를 받는다(`evaluate` 가 그 순서를 지킨다)."""
    if mode != SHADOW:
        raise ValueError(f"mode={mode!r}: OQ-17(안전 동작 전순서) 전에는 shadow 만 켠다")
    iid = _intent_id(intent)
    try:
        return _guard(intent, dc, state, model, mode)
    except Exception as e:                                   # 닫힌 쪽으로
        return GuardResult(iid, DENY, mode, "E", (), [f"[E] Guard 예외: {type(e).__name__}: {e}"], None)


def _guard(it: ActionIntent, dc: DCView, state: StateView, model: GuardModel, mode: str) -> GuardResult:
    if not isinstance(it, ActionIntent):
        raise TypeError(f"ActionIntent 가 아니다 ({type(it).__name__})")
    spec = model.specs[it.action]
    fails: dict = {}                                       # 규칙 -> [까닭]
    refs: list = []

    # D -- 결정 문맥이 불완전 · 낡았는데 위험 등급 행동. 목적의 안전 기본 후보는 막지 않는다(DATA_FLOW §6.1)
    stale = stale_in_scope(it, dc)
    if spec.risk in model.risky and it.action not in dc.default_decision and (not dc.complete or stale):
        why = ([] if dc.complete else [f"DC 가 불완전하다(쓸 수 없는 필수 상태 {sorted(dc.missing_required)})"]) + (
            [f"필수 · 의도가 쓴 키 가운데 낡은 것 {stale}"] if stale else [])
        fails["D"] = [f"{it.action}({spec.risk}): " + " · ".join(why)]

    node = state.entities.get(it.target) if it.target is not None else None
    if node is not None:
        refs.append(f"{it.target}@{node.version}")

    # A5 -- 결정이 본 판과 지금 판
    if it.target is not None:
        if node is None:
            fails["A5"] = [f"{it.target} 가 지금 상태에 없다"]
        elif it.target not in dc.seen:
            fails["A5"] = [f"{it.target} 의 본 판이 결정 문맥에 없다"]
        elif node.version != dc.seen[it.target]:
            fails["A5"] = [f"{it.target} 가 결정 문맥을 지은 뒤 바뀌었다(판 {dc.seen[it.target]} -> {node.version})"]

    # A6 -- 사전조건이 보는 속성이 지금 있고 낡지 않았나 · 지금 참인가
    why = _unmet(spec, it.target, node, refs)
    if why:
        fails["A6"] = why

    # A7 -- 허가
    if spec.risk in GRANT_RISKS and spec.name not in model.grants:
        fails["A7"] = [f"{spec.name} 는 {spec.risk} 인데 허가가 없다"]

    # A8 -- 같은 대상 · 같은 판에서 이미 ALLOW 한 같은 의도
    version = node.version if node is not None else -1
    if repeat_key(it, version) in state.allowed:
        fails["A8"] = [f"같은 의도를 {it.target} 판 {version} 에서 이미 ALLOW 했다"]

    if not fails:
        return GuardResult(it.id, ALLOW, mode, PASS, refs, [f"{spec.name}({spec.risk}) -> {it.target}"], None)
    rule = next(r for r in GUARD_ORDER if r in fails)
    reasons = [f"[{r}] {w}" for r in GUARD_ORDER if r in fails for w in fails[r]]
    if "D" in fails and dc.default_action is not None and dc.default_action in dc.default_decision:
        if dc.default_action not in model.specs:            # BD-104: 실행기 행동(ActionSpec)이 아니면 갈아 끼우지 않는다
            reasons.append(f"[D] 안전 기본 {dc.default_action} 은 실행기 행동이 아니다(ActionSpec 없음) -- 갈아 끼우지 않는다")
            return GuardResult(it.id, DENY, mode, rule, refs, reasons, None)
        reasons.append(f"[D] 목적의 기본 행동 {dc.default_action} 로 갈아 끼운다")
        return GuardResult(it.id, SAFE_ACTION, mode, rule, refs, reasons, dc.default_action)
    return GuardResult(it.id, DENY, mode, rule, refs, reasons, None)


def _unmet(spec, target, node, refs) -> list:
    """MS `query.unmet` 과 같은 뜻. 비었으면 지금 쓸 수 있다."""
    if target is None:
        return [f"{spec.name} 는 겨냥이 없는데 사전조건이 있다"] if spec.preconditions else []
    if node is None:
        return [f"실체 {target} 가 없다"]
    if spec.target_model not in ("*", node.model):
        return [f"{spec.name} 는 {spec.target_model} 용인데 {target} 는 {node.model}"]
    out = []
    names = predicate.props_of(spec.preconditions)
    refs.extend(f"{target}.{p}" for p in names)
    for p in names:
        pv = node.props.get(p)
        if pv is None or pv.stale:
            age = None if pv is None else pv.age
            out.append(f"{target}.{p} 가 " + ("없다" if pv is None or age is None else f"낡았다({age:.0f}s)"))
    if not out:
        vals = node.values()
        for p in spec.preconditions:
            if not predicate.holds(p, vals):
                out.append(f"사전조건 {list(p)} 가 {target} 에서 거짓 ({p[0]}={vals.get(p[0])!r})")
    return out


# ── 둘을 잇는 길 ─────────────────────────────────────────────────────────────

def evaluate(intent, dc: DCView, state: StateView, model: GuardModel, mode: str = SHADOW):
    """VALIDATE → GUARD. VALIDATE 가 막으면 GUARD 는 돌지 않고, GuardResult 는 그 규칙으로 DENY 다(닫는 쪽으로만).
    ARBITRATE 는 후보가 하나라 고를 것이 없다(BD-24: 지금 옮길 규칙 없음)."""
    if mode != SHADOW:
        raise ValueError(f"mode={mode!r}: OQ-17(안전 동작 전순서) 전에는 shadow 만 켠다")
    v = validate(intent, dc, model)
    if not v.ok:
        return v, GuardResult(v.intent_id, DENY, mode, v.rule, (), [f"[{v.rule}] {r}" for r in v.reasons], None)
    it, _ = _as_intent(intent)
    return v, guard(it, dc, state, model, mode)
