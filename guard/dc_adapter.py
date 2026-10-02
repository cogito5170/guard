"""DC 결정 문맥(데이터) → DCView (baseline#7 CMD-G2 · F5).

Guard 는 DC 코드를 import 하지 않는다. DC 가 내는 **데이터**만 읽는다:

    record    DC `DecisionContext.to_dict()` = {"digest", "core", "provenance"}   digest 를 다시 계산해 맞춰 본다
              또는 `core_dict()` = {"id", <core 칸>}                              맞춰 볼 digest 가 없다(id 를 그대로 믿는다)
    purpose   DC 목적 명세(`Purpose`)의 데이터(`dataclasses.asdict`). 읽는 칸: name · version · refs[].role/name/required ·
              default_decision. `complete` · `missing_required` 는 core 에 없고 목적 명세의 필수 여부로 계산하는 투영이라 필요하다
              (DC `project.validity` 와 같은 식)

옮기는 법
- `dc_id`             record 의 id(`"dc-" + digest 앞 16 자`)
- `complete`          필수 키 가운데 쓸 수 없고(OBSERVED · DERIVED · INFERRED 가 아님) NOT_APPLICABLE 도 아닌 것이 없다
- `missing_required`  그 키들. 목적이 필수로 부른 키가 core 에 아예 없으면 그것도 넣는다(닫는 쪽)
- `stale_keys`        core 상태 가운데 STALE 인 키 + 질의 행 속성 가운데 STALE 인 것(`"<질의>/<행>.<속성>"`)
- `required_keys`     core 상태 가운데 목적이 필수로 부른 키. D 는 낡은 키 가운데 필수 ∪ 의도의 used_keys 만 본다(BD-103)
- `default_decision`  목적의 후보(순서 그대로) · `default_action` core 의 값(DC 가 능력으로 고른 것)
- `offers`            core 의 가능 행동은 목적 단위라 겨냥이 없다 → `{행동: [None]}`. 겨냥 있는 행동(MS 도구 등)과 결정이 본 실체의 판은
                      DC 에 없다 -- 런타임이 `offers` · `seen` 으로 넘긴다(F4)

목적의 이름 · 판본이 core 와 다르면 투영하지 않는다(DC `spec_of` 와 같다). 맞지 않는 것은 모두 ViewError 다 -- 부르는 쪽은
그것을 DENY(E)로 다룬다.
"""
from __future__ import annotations

import hashlib
import json

from .views import DCView, ViewError

USABLE = ("OBSERVED", "DERIVED", "INFERRED")         # DC model.USABLE 과 같은 낱말
NOT_APPLICABLE, STALE = "NOT_APPLICABLE", "STALE"
CORE_KEYS = {"purpose", "purpose_version", "default_action", "queries", "as_of", "subject", "states", "constraints",
             "actions"}
PURPOSE_KEYS = {"name", "version", "refs", "constraints", "actions", "meaning", "queries", "query_sources",
                "default_decision"}


def _digest(body: dict) -> str:
    """DC `snapshot.digest_of` 와 같은 바이트열의 sha256."""
    text = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _core_and_id(record: dict) -> "tuple[dict, str]":
    if not isinstance(record, dict):
        raise ViewError(f"DC 문맥: 객체가 아니다 ({type(record).__name__})")
    if set(record) == {"digest", "core", "provenance"}:
        body = {"core": record["core"], "provenance": record["provenance"]}
        if not isinstance(record["digest"], str) or _digest(body) != record["digest"]:
            raise ViewError("DC 문맥: 내용이 digest 와 맞지 않는다")
        core, dc_id = record["core"], "dc-" + record["digest"][:16]
    elif "id" in record:
        core, dc_id = {k: v for k, v in record.items() if k != "id"}, record["id"]
    else:
        raise ViewError(f"DC 문맥: {{digest, core, provenance}} 도 core_dict({{id, …}}) 도 아니다 ({sorted(record)})")
    if not isinstance(core, dict) or set(core) != CORE_KEYS:
        got = set(core) if isinstance(core, dict) else set()
        raise ViewError(f"DC core: 칸이 다르다(모르는 {sorted(got - CORE_KEYS)} · 빠진 {sorted(CORE_KEYS - got)})")
    if not isinstance(dc_id, str) or not dc_id.startswith("dc-"):
        raise ViewError(f"DC 문맥: id 꼴이 아니다 {dc_id!r}")
    return core, dc_id


def _role_name(key: str) -> "tuple[str, str]":
    head, name = key.rsplit(".", 1)
    return head.split("[", 1)[0], name


def _required(purpose: dict) -> "set[tuple[str, str]]":
    out = set()
    for r in purpose["refs"]:
        if not isinstance(r, dict) or not {"role", "name"} <= set(r):
            raise ViewError(f"DC 목적: refs 의 꼴이 아니다 {r!r}")
        if r.get("required", True):                  # DC StateRef.required 기본값은 참이다
            out.add((r["role"], r["name"]))
    return out


def dcview_from_dc(record: dict, purpose: dict, *, offers: "dict | None" = None,
                   seen: "dict | None" = None) -> DCView:
    core, dc_id = _core_and_id(record)
    if not isinstance(purpose, dict) or set(purpose) - PURPOSE_KEYS or not {"name", "version", "refs"} <= set(purpose):
        raise ViewError(f"DC 목적: 꼴이 아니다 (칸 {sorted(purpose) if isinstance(purpose, dict) else purpose!r})")
    if (purpose["name"], purpose["version"]) != (core["purpose"], core["purpose_version"]):
        raise ViewError(f"DC 목적 {purpose['name']}@{purpose['version']} 가 문맥의 "
                        f"{core['purpose']}@{core['purpose_version']} 가 아니다 -- 투영하지 않는다")

    states = core["states"]
    if not isinstance(states, dict) or not all(isinstance(v, list) and len(v) == 2 for v in states.values()):
        raise ViewError("DC core.states: {키: [값, 유효성]} 이어야 한다")
    required = _required(purpose)
    missing = [k for k, (_, st) in states.items()
               if _role_name(k) in required and st not in USABLE and st != NOT_APPLICABLE]
    present = {_role_name(k) for k in states}
    missing += [f"{r}.{n}" for r, n in sorted(required - present)]
    stale = [k for k, (_, st) in states.items() if st == STALE]
    for qname, q in sorted(core["queries"].items()):
        for row in q["rows"]:
            stale += [f"{qname}/{row['id']}.{p}" for p, (_, st) in sorted(row["props"].items()) if st == STALE]

    acts = core["actions"]
    if not isinstance(acts, list) or not all(isinstance(a, str) and a for a in acts):
        raise ViewError("DC core.actions: 행동 이름의 목록이어야 한다")
    offered = {a: [None] for a in acts}
    for a, targets in (offers or {}).items():
        offered[a] = list(dict.fromkeys(offered.get(a, []) + list(targets)))

    view = DCView(dc_id=dc_id, offers=offered, seen=dict(seen or {}), complete=not missing,
                  stale_keys=tuple(sorted(stale)), default_decision=tuple(purpose.get("default_decision", ())),
                  default_action=core["default_action"], missing_required=tuple(sorted(missing)),
                  required_keys=tuple(sorted({k for k in states if _role_name(k) in required})))
    view.check()
    return view
