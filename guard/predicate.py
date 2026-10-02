"""술어 `[속성, 연산, 값]` -- ActionSpec 사전조건의 언어. MS `ms/predicate.py` 와 **같은 뜻**이다(대조 시험이 붙든다).

Guard 는 MS 를 import 하지 않으므로(BD-07) 여기 따로 둔다. 같은 언어가 두 곳에 있는 것은 Model 의 술어 언어에 아직 공용
집이 없기 때문이다(docs/GUARD.md §5 F1).

- `eval` 없음. 연산은 아래 표가 전부다.
- 값 자리에 다른 속성을 걸 수 있다: `{"prop": 이름, "mul": 수}`. 걸린 속성이 없거나 수가 아니면 거짓.
- 속성이 없으면 거짓(`exists` · `missing` 은 그것을 묻는 연산). 비교할 수 없는 값도 거짓 -- 모르는 것을 참으로 세지 않는다.
"""
from __future__ import annotations

OPS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
}


def check(pred) -> list:
    """모양이 틀린 술어. 문제 목록(비었으면 성하다)."""
    if not isinstance(pred, (list, tuple)) or len(pred) not in (2, 3):
        return [f"술어는 [속성, 연산, 값] 이어야 한다: {pred!r}"]
    if len(pred) == 2:
        return [] if pred[1] in ("exists", "missing") else [f"값 없는 연산은 exists · missing 뿐: {pred!r}"]
    if pred[1] not in OPS:
        return [f"모르는 연산 {pred[1]!r}"]
    if pred[1] in ("in", "not_in") and not isinstance(pred[2], (list, tuple)):
        return [f"{pred[1]} 의 값은 목록이어야 한다: {pred!r}"]
    if isinstance(pred[2], dict):
        if set(pred[2]) - {"prop", "mul"} or not isinstance(pred[2].get("prop"), str):
            return [f"속성 참조는 {{\"prop\": 이름, \"mul\": 수}} 꼴이어야 한다: {pred!r}"]
        if pred[1] not in ("<", "<=", ">", ">=", "==", "!="):
            return [f"속성 참조는 비교 연산에만: {pred!r}"]
    return []


def _rhs(v, values):
    if isinstance(v, dict) and "prop" in v:
        ref = values.get(v["prop"])
        if ref is None or isinstance(ref, bool) or not isinstance(ref, (int, float)):
            return None
        return ref * v.get("mul", 1)
    return v


def holds(pred, values: dict) -> bool:
    prop, op = pred[0], pred[1]
    if op == "exists":
        return values.get(prop) is not None
    if op == "missing":
        return values.get(prop) is None
    if values.get(prop) is None:
        return False
    rhs = _rhs(pred[2], values)
    if rhs is None:
        return False
    try:
        return bool(OPS[op](values[prop], rhs))
    except TypeError:
        return False


def props_of(preds) -> list:
    """술어들이 읽는 속성(걸린 속성 포함). 처음 나온 순서."""
    out = []
    for p in preds:
        for name in [p[0]] + ([p[2]["prop"]] if len(p) > 2 and isinstance(p[2], dict) and "prop" in p[2] else []):
            if name not in out:
                out.append(name)
    return out
