"""Guard 가 읽는 입력 셋 -- 결정이 **본 것**(DCView) · **지금** 상태(StateView) · 규칙(GuardModel).

Guard 는 Policy · CR · MS 를 import 하지 않는다(BD-07). 그래서 입력을 데이터 꼴로 받는다. 누가 채우든(MS 의 맥락 · DC 의
결정 문맥 · 시험) 같은 꼴이다. 셋 다 닫힌 꼴이다: `from_dict` 는 모르는 칸을 거절한다.

DCView      한 결정이 본 문맥. VALIDATE 의 근거(A1–A3)와 GUARD 의 "본 판"(A5) · 완전성(D)
StateView   배차 직전의 **지금** 상태. 실체마다 판 · 속성 값 · 낡음. 그리고 이미 ALLOW 한 열쇠(A8)
GuardModel  ActionSpec(Model, BD-31 의 투영: 대상 모형 · 인자 · 사전조건 · 위험 등급) · 허가 · 위험 등급의 정의
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields

from . import predicate

RISKS = ("read", "local", "external", "irreversible")
DEFAULT_RISKY = ("external", "irreversible")       # D 가 막는 위험 등급(가정 -- docs/GUARD.md §4)


class ViewError(ValueError):
    pass


def _closed(cls, d: dict, name: str) -> dict:
    if not isinstance(d, dict):
        raise ViewError(f"{name}: 객체가 아니다 ({type(d).__name__})")
    known = {f.name for f in fields(cls)}
    extra = sorted(set(d) - known, key=str)
    if extra:
        raise ViewError(f"{name}: 모르는 칸 {extra}")
    return {k: d[k] for k in known if k in d}


# ── 결정이 본 것 ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DCView:
    dc_id: str
    offers: dict                      # 행동 이름 -> [겨냥 실체, ...]  문맥이 그 행동을 그 대상에 내놓았다(A1 · A3)
    seen: dict                        # 실체 -> 판(int)  결정이 값을 **본** 실체와 그때의 판(A2 · A5)
    decisions: dict = field(default_factory=dict)   # 실체 -> 문맥이 그 실체를 어떻게 다뤘나(KEEP · SUMMARIZE · RETRIEVE · DEFER · DROP …). 까닭 글에만
    handles: dict = field(default_factory=dict)     # 손잡이 -> [실체, ...]  까닭 글에만
    complete: bool = True             # 목적의 필수 상태가 모두 쓸 수 있었나(DC `complete`)
    stale_keys: tuple = ()            # 결정 문맥 안에서 낡았던 키
    default_decision: tuple = ()      # 목적의 안전 기본 결정 후보(DC `Purpose.default_decision`, BD-23 · BD-76)
    default_action: "str | None" = None   # DC 가 고른 기본 행동(능력 있는 첫 후보, DC `core.default_action`)
    missing_required: tuple = ()      # 쓸 수 없던 필수 키(DC 투영 `missing_required`). 까닭 글에만 -- 판정은 complete 로

    @classmethod
    def from_dict(cls, d: dict) -> "DCView":
        kw = _closed(cls, d, "DCView")
        for k in ("stale_keys", "default_decision", "missing_required"):
            if k in kw:
                kw[k] = tuple(kw[k])
        v = cls(**kw)
        v.check()
        return v

    def check(self):
        if not isinstance(self.dc_id, str) or not self.dc_id:
            raise ViewError("DCView.dc_id: 빈 것이 아닌 문자열이어야 한다")
        if not isinstance(self.offers, dict) or not all(isinstance(t, (list, tuple)) for t in self.offers.values()):
            raise ViewError("DCView.offers: {행동: [대상, ...]} 이어야 한다")
        if not isinstance(self.seen, dict) or not all(
                isinstance(n, int) and not isinstance(n, bool) for n in self.seen.values()):
            raise ViewError("DCView.seen: {실체: 판(int)} 이어야 한다")
        if not isinstance(self.complete, bool):
            raise ViewError("DCView.complete: bool 이어야 한다")
        if self.default_action is not None and self.default_action not in self.default_decision:
            raise ViewError(f"DCView.default_action {self.default_action!r} 가 default_decision 밖이다")


# ── 지금 상태 ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Prop:
    value: object
    stale: bool                       # 값이 없거나 TTL 을 넘겼다(상태 저장소가 정한다)
    age: "float | None" = None        # 까닭 글에만


@dataclass(frozen=True)
class Entity:
    model: str
    version: int
    props: dict                       # 이름 -> Prop

    def values(self) -> dict:
        return {k: p.value for k, p in self.props.items()}


@dataclass(frozen=True)
class StateView:
    entities: dict                    # 실체 -> Entity
    allowed: frozenset = frozenset()  # 이미 ALLOW 한 되풀이 열쇠(`guard.repeat_key`). Guard 는 순수 함수라 호출자가 더한다

    @classmethod
    def from_dict(cls, d: dict) -> "StateView":
        kw = _closed(cls, d, "StateView")
        ents = {}
        for nid, e in (kw.get("entities") or {}).items():
            e = dict(e)
            extra = set(e) - {"model", "version", "props"}
            if extra:
                raise ViewError(f"StateView.entities[{nid}]: 모르는 칸 {sorted(extra)}")
            props = {}
            for p, pv in (e.get("props") or {}).items():
                extra = set(pv) - {"value", "stale", "age"}
                if extra or "stale" not in pv or not isinstance(pv["stale"], bool):
                    raise ViewError(f"StateView.entities[{nid}].props[{p}]: {{value, stale(bool), age}} 이어야 한다")
                props[p] = Prop(pv.get("value"), pv["stale"], pv.get("age"))
            v = e.get("version")
            if not isinstance(v, int) or isinstance(v, bool):
                raise ViewError(f"StateView.entities[{nid}].version: int 이어야 한다")
            ents[nid] = Entity(e["model"], v, props)
        return cls(ents, frozenset(kw.get("allowed", ())))


# ── 규칙 ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ActionSpec:
    name: str
    target_model: "str | None" = "*"  # "*" 아무 모형 · None 겨냥 없는 행동(STOP · ESCALATE)
    params: dict = field(default_factory=dict)          # 이름 -> {"type", "min", "max", "values", "unit", "required"}
    preconditions: tuple = ()         # 대상의 **지금** 상태에 대한 술어 [속성, 연산, 값]
    risk: str = "local"

    def __post_init__(self):
        if self.risk not in RISKS:
            raise ViewError(f"ActionSpec {self.name}: 모르는 위험 등급 {self.risk!r}")
        object.__setattr__(self, "preconditions", tuple(tuple(p) if isinstance(p, list) else p
                                                        for p in self.preconditions))
        for p in self.preconditions:
            bad = predicate.check(p)
            if bad:
                raise ViewError(f"ActionSpec {self.name}: {bad[0]}")

    @classmethod
    def from_dict(cls, d: dict) -> "ActionSpec":
        return cls(**_closed(cls, d, "ActionSpec"))


@dataclass(frozen=True)
class GuardModel:
    specs: dict                       # 이름 -> ActionSpec
    grants: frozenset = frozenset()   # external · irreversible 을 허락한 행동 이름(A7)
    risky: tuple = DEFAULT_RISKY      # DC 가 불완전 · 낡았을 때 막는 위험 등급(D)

    @classmethod
    def from_dict(cls, d: dict) -> "GuardModel":
        kw = _closed(cls, d, "GuardModel")
        specs = {}
        for s in kw.get("specs", ()):
            s = s if isinstance(s, ActionSpec) else ActionSpec.from_dict(s)
            specs[s.name] = s
        risky = tuple(kw.get("risky", DEFAULT_RISKY))
        bad = [r for r in risky if r not in RISKS]
        if bad:
            raise ViewError(f"GuardModel.risky: 모르는 위험 등급 {bad}")
        return cls(specs, frozenset(kw.get("grants", ())), risky)
