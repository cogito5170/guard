"""Guard 의 꼴 둘 -- ValidationResult(VALIDATE) · GuardResult(GUARD). baseline `SCHEMA_PROPOSAL.md` §2 표.

규칙 (action 계약 `action-contract/1` 과 같은 방식)
- **닫힌 꼴.** `from_dict` 는 모르는 칸 · 빠진 칸 · 다른 판본(`schema`)을 거절한다. 지을 때 칸마다 타입 · 값을 검사한다.
- **id 는 내용 해시다.** 나머지 칸 전부의 정준 JSON(`action.canonical`) → sha256 앞 16 hex. `from_dict` 가 다시 계산해
  맞지 않으면 거절한다.
- 표와 다른 곳은 칸 옆 주석과 `docs/GUARD.md` §3 에 까닭이 있다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, fields

from action.canonical import digest
from action.forms import INTENT_ID

VALIDATION_SCHEMA = "validation-result/1"
GUARD_SCHEMA = "guard-result/1"

ALLOW, DENY, SAFE_ACTION = "ALLOW", "DENY", "SAFE_ACTION"
VERDICTS = (ALLOW, DENY, SAFE_ACTION)
SHADOW, ENFORCE = "shadow", "enforce"
MODES = (SHADOW, ENFORCE)

# 규칙 이름. A0–A8 · E 는 MS `arbiter.py` 와 같은 뜻이다(BD-24 배분). D 는 새 것(DATA_FLOW §6.5).
VALIDATE_RULES = ("A0", "A1", "A2", "A3", "A4", "E")
GUARD_RULES = ("D", "A5", "A6", "A7", "A8", "E")
PASS = "0"                                   # 걸린 규칙이 없다(MS 의 ALLOW rule "0" 과 같다)

STATE_REF = re.compile(r"^[^\s@]+(@\d+|\.[^\s@]+)$")     # "<실체>@<판>" 또는 "<실체>.<속성>"


class FormError(ValueError):
    """꼴에 맞지 않는다. `errors` 에 까닭 전부."""

    def __init__(self, form: str, errors: "list[str]"):
        self.errors = list(errors)
        super().__init__(f"{form}: {'; '.join(self.errors)}")


def _strs(v, name, errs, nonempty_items=True):
    if not isinstance(v, tuple) or not all(isinstance(x, str) and (x or not nonempty_items) for x in v):
        errs.append(f"{name}: 문자열의 목록이어야 한다")


class _Form:
    SCHEMA: str
    ID: str
    ID_PREFIX: str

    def _errors(self) -> "list[str]":
        raise NotImplementedError

    def __post_init__(self):
        for f in fields(self):                        # 목록은 tuple 로 굳힌다(frozen · 해시 입력이 같은 꼴)
            v = getattr(self, f.name)
            if isinstance(v, list):
                object.__setattr__(self, f.name, tuple(v))
        errs = self._errors()
        if errs:
            raise FormError(type(self).__name__, errs)

    def body(self) -> dict:
        return {f.name: (list(v) if isinstance(v := getattr(self, f.name), tuple) else v) for f in fields(self)}

    def to_dict(self) -> dict:
        d = self.body()
        d[self.ID] = f"{self.ID_PREFIX}{digest(self.body())}"
        return d

    @property
    def id(self) -> str:
        return self.to_dict()[self.ID]

    @classmethod
    def from_dict(cls, d: dict):
        name = cls.__name__
        if not isinstance(d, dict):
            raise FormError(name, [f"객체가 아니다 ({type(d).__name__})"])
        known = {f.name for f in fields(cls)} | {cls.ID}
        errs = [f"모르는 칸 {k!r}" for k in sorted(set(d) - known, key=str)]
        errs += [f"빠진 칸 {k!r}" for k in sorted(known - set(d))]
        if errs:
            raise FormError(name, errs)
        obj = cls(**{f.name: d[f.name] for f in fields(cls)})
        if d[cls.ID] != obj.id:
            raise FormError(name, [f"{cls.ID}: 내용과 맞지 않는다 ({d[cls.ID]!r} ≠ {obj.id!r})"])
        return obj


def _common(self, rules, e):
    if self.schema != self.SCHEMA:
        e.append(f"schema: {self.schema!r} (기대 {self.SCHEMA!r})")
    if not isinstance(self.intent_id, str) or not INTENT_ID.match(self.intent_id):
        e.append(f"intent_id: 꼴이 아니다 {self.intent_id!r}")
    if self.rule not in rules + (PASS,):
        e.append(f"rule: {self.rule!r} (기대 {rules + (PASS,)})")
    _strs(self.reasons, "reasons", e)


@dataclass(frozen=True)
class ValidationResult(_Form):
    """VALIDATE(A0–A4): 의도가 꼴이 맞고 **자기 DC 안에서** 근거가 있나. 지금 상태는 보지 않는다(그것은 GUARD)."""
    intent_id: str
    ok: bool
    rule: str                    # 걸린 첫 규칙. ok 면 "0"
    reasons: tuple
    schema: str = VALIDATION_SCHEMA

    SCHEMA = VALIDATION_SCHEMA
    ID = "validation_id"
    ID_PREFIX = "val-"

    def _errors(self):
        e = []
        _common(self, VALIDATE_RULES, e)
        if not isinstance(self.ok, bool):
            e.append(f"ok: bool 이 아니다 ({self.ok!r})")
        elif self.ok != (self.rule == PASS):
            e.append(f"ok={self.ok} 와 rule={self.rule!r} 가 맞지 않는다")
        return e


@dataclass(frozen=True)
class GuardResult(_Form):
    """GUARD(A5–A8 · D): 고른 의도를 **지금** 실행해도 되나. 닫는 쪽으로만 간다."""
    intent_id: str
    verdict: str                 # ALLOW · DENY · SAFE_ACTION
    mode: str                    # shadow · enforce. 판정은 모드와 무관하다 -- 모드는 그 판정을 따를지만 정한다
    rule: str                    # 판정을 정한 규칙. ALLOW 면 "0"
    state_refs: tuple            # 본 **지금** 상태: "<실체>@<판>" · "<실체>.<속성>". 정렬, 겹침 없음
    reasons: tuple               # 걸린 규칙 **전부**의 까닭("[A6] …"). 제약은 논리곱이다
    safe_action: "str | None"    # **표에 없던 칸.** SAFE_ACTION 일 때 갈아 끼운 행동 이름(목적의 default_decision 안). 그 밖에는 None
    schema: str = GUARD_SCHEMA

    SCHEMA = GUARD_SCHEMA
    ID = "guard_id"
    ID_PREFIX = "grd-"

    def __post_init__(self):
        if isinstance(self.state_refs, (list, tuple)) and all(isinstance(x, str) for x in self.state_refs):
            object.__setattr__(self, "state_refs", tuple(sorted(self.state_refs)))
        super().__post_init__()

    def _errors(self):
        e = []
        _common(self, GUARD_RULES + VALIDATE_RULES, e)
        if self.verdict not in VERDICTS:
            e.append(f"verdict: {self.verdict!r} (기대 {VERDICTS})")
        if self.mode not in MODES:
            e.append(f"mode: {self.mode!r} (기대 {MODES})")
        if (self.verdict == ALLOW) != (self.rule == PASS):
            e.append(f"verdict={self.verdict!r} 와 rule={self.rule!r} 가 맞지 않는다")
        if (self.verdict == SAFE_ACTION) != (self.safe_action is not None):
            e.append("safe_action 은 SAFE_ACTION 일 때만, 그때는 반드시 있다")
        if self.safe_action is not None and (not isinstance(self.safe_action, str) or not self.safe_action):
            e.append(f"safe_action: 빈 것이 아닌 문자열이 아니다 ({self.safe_action!r})")
        _strs(self.state_refs, "state_refs", e)
        if isinstance(self.state_refs, tuple):
            if len(set(self.state_refs)) != len(self.state_refs):
                e.append("state_refs: 겹침")
            bad = [r for r in self.state_refs if isinstance(r, str) and not STATE_REF.match(r)]
            if bad:
                e.append(f"state_refs: 꼴이 아니다 {bad}")
        return e


FORMS = (ValidationResult, GuardResult)
