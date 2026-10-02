"""A4 -- 인자가 ActionSpec 의 params 와 맞나. MS `ToolSpec.check_args` + `PropertySpec.validate` 와 같은 뜻이다.

params: 이름 -> {"type": number · integer · string · bool · enum, "min", "max", "values", "unit", "required"(기본 참)}
"""
from __future__ import annotations

TYPES = ("number", "integer", "string", "bool", "enum")


def _problem(name: str, ps: dict, v) -> "str | None":
    t = ps.get("type", "number")
    unit = ps.get("unit", "")
    if t == "number":
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return f"{name}: 수가 아니다 ({v!r})"
        v = float(v)
        if v != v:
            return f"{name}: NaN"
    elif t == "integer":
        if isinstance(v, bool) or not isinstance(v, int):
            if isinstance(v, float) and v.is_integer():
                v = int(v)
            else:
                return f"{name}: 정수가 아니다 ({v!r})"
    elif t == "string":
        if not isinstance(v, str):
            return f"{name}: 문자열이 아니다 ({v!r})"
    elif t == "bool":
        if not isinstance(v, bool):
            return f"{name}: 참거짓이 아니다 ({v!r})"
    elif t == "enum":
        if v not in (ps.get("values") or []):
            return f"{name}: {v!r} 는 {ps.get('values')} 밖이다"
    else:
        return f"{name}: 모르는 타입 {t!r}"
    if t in ("number", "integer"):
        if ps.get("min") is not None and v < ps["min"]:
            return f"{name}: {v} < 최소 {ps['min']}{unit}"
        if ps.get("max") is not None and v > ps["max"]:
            return f"{name}: {v} > 최대 {ps['max']}{unit}"
    return None


def check_args(params: dict, args) -> list:
    """문제 목록. 비었으면 맞다."""
    if not isinstance(args, dict):
        return ["args 가 객체가 아니다"]
    out = [f"모르는 인자 {k}" for k in args if k not in params]
    for k, ps in params.items():
        if k not in args:
            if ps.get("required", True):
                out.append(f"인자 {k} 가 없다")
            continue
        p = _problem(k, ps, args[k])
        if p:
            out.append(p)
    return out
