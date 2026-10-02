"""DC 의 **실제 빌더**로 결정 문맥을 지어 시험용 고정 파일을 쓴다 (baseline#7 CMD-G2 끝난 기준 1).

    python3 eval/dc_fixtures.py           # DC 를 옆 디렉터리(또는 DC_REPO)에서 찾아 tests/fixtures/dc_contexts.json 을 다시 쓴다
    python3 eval/dc_fixtures.py --check   # 다시 지은 것이 저장된 파일과 같은지만 본다(DC 가 바뀌었나)

Guard 패키지는 DC 를 import 하지 않는다. 이 파일만 DC 를 읽기 전용으로 부른다(공개 API: StateRecord · StaticSource ·
DecisionContextBuilder · PURPOSES). 사례마다 저장하는 것:
    record          DC `ctx.to_dict()` -- 어댑터의 입력
    purpose         DC 목적 명세의 `dataclasses.asdict` -- 어댑터의 입력
    dc_projection   DC 가 **스스로** 계산한 투영(`ctx.validity` · 상태 view 의 STALE · core.default_action) -- 어댑터 출력과 맞대는 정답
"""
from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "fixtures" / "dc_contexts.json"

MIN = 60_000.0
NOW = 1_000_000.0
LEVELS = ("HIGH", "MEDIUM", "LOW")
SENSOR_DOMAINS = {     # DC 시험(helpers.py)과 같은 값 집합
    "context_pressure": ("BELOW_CONTEXT_LIMIT", "BELOW_COMPACTION_THRESHOLD", "ABOVE_COMPACTION_THRESHOLD",
                         "AT_CONTEXT_LIMIT"),
    "execution_health": ("NO_FAILURE_OBSERVED", "RECOVERED_FAILURES", "UNRESOLVED_FAILURES", "NO_TOOL_RUN_YET"),
    "tool_execution_health": ("NO_FAILURE_OBSERVED", "RECOVERED_FAILURES", "UNRESOLVED_FAILURES"),
    "completion_state": ("RUNNING", "ENDED_NORMALLY", "ENDED_BY_LIMIT", "ENDED_WITH_ERROR"),
    "progress_state": ("STALLED", "NO_STALL_DETECTED"),
    "resource_state": ("WITHIN_BUDGET", "BUDGET_EXHAUSTED"),
    "rate_limit_state": ("AVAILABLE", "EXHAUSTED"),
    "runtime_reliability": ("NO_FAILURE_OBSERVED", "FAILURE_OBSERVED"),
}


def find_dc() -> "pathlib.Path | None":
    for p in filter(None, [os.environ.get("DC_REPO"), ROOT.parent / "DC", ROOT.parent / "dc",
                           ROOT.parent / "cogito5170" / "dc"]):
        p = pathlib.Path(p)
        if (p / "dc" / "builder.py").exists():
            return p.resolve()
    return None


def load_dc():
    p = find_dc()
    if p is None:
        return None
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
    import dc
    return dc


def _rec(dc, source, entity, name, value, status="INFERRED", *, at=NOW - MIN, ttl=10 * MIN, basis="DEFINITIONAL"):
    ev = () if value is None else (f"{entity}/{name}_metric@1",)
    return dc.StateRecord(source, entity, name, value, status, basis, rule_id=name, rule_version=1, evidence_refs=ev,
                          observed_at_ms=at, ttl_ms=ttl)


def _sensor(dc, run="r1", **over):
    """over: 상태 이름 -> (값, 유효성, 관측 시각) 로 바꾼다."""
    a, t, rt = f"agent:{run}", f"task:{run}", f"runtime:{run}"
    base = {
        (a, "context_pressure"): ("BELOW_COMPACTION_THRESHOLD", "INFERRED", NOW - MIN),
        (a, "execution_health"): ("UNRESOLVED_FAILURES", "INFERRED", NOW - MIN),
        (a, "resource_state"): (None, "NOT_APPLICABLE", NOW - MIN),
        (t, "progress_state"): (None, "UNKNOWN", NOW - MIN),
        (t, "completion_state"): ("RUNNING", "INFERRED", NOW - MIN),
        (rt, "rate_limit_state"): ("AVAILABLE", "INFERRED", NOW - MIN),
        (rt, "runtime_reliability"): ("NO_FAILURE_OBSERVED", "INFERRED", NOW - MIN),
        (f"tool:{run}:Bash", "tool_execution_health"): ("RECOVERED_FAILURES", "INFERRED", NOW - MIN),
    }
    for (ent, name) in list(base):
        if name in over:
            base[(ent, name)] = over[name]
    rows = [_rec(dc, "sensor", e, n, v, st, at=at) for (e, n), (v, st, at) in base.items()]
    return dc.StaticSource("sensor", rows, SENSOR_DOMAINS, {"config": "guard-fixture-1"})


def _ms(dc, session="session:s1"):
    names = ("token_budget_pressure", "context_pressure", "latency_pressure", "task_complexity", "answer_reliability",
             "correction_rate", "retry_pressure")
    rows = [_rec(dc, "ms", session, n, "LOW", ttl=None, basis="OPERATOR_ASSUMED") for n in names]
    return dc.StaticSource("ms", rows, {n: LEVELS for n in names}, {"model": "usage-model-1"})


class _World:
    """MS 세계 그래프 자리의 소스(DC 시험의 FakeWorld 와 같은 꼴). 질의 행 하나에 STALE 속성이 있다."""
    name, authoritative = "ms_world", True

    def read(self, e, n, now):
        import dc
        return dc.StateRecord(self.name, e, n, None, "UNKNOWN", "OBSERVED")

    def domain(self, e, n):
        return None

    def versions(self):
        return {"graph": "guard-fixture"}

    def query(self, spec, now):
        return {"matched": 2, "rows": [
            {"id": "srv07", "model": "Server", "must": True, "edges": [],
             "props": {"status": {"value": "critical", "status": "INFERRED", "ref": "derived:temp_c"},
                       "fan_rpm": {"value": 1200, "status": "STALE", "ref": "t3", "observed_at_ms": NOW - 9e6}}},
            {"id": "srv05", "model": "Server",
             "props": {"status": {"value": "hot", "status": "INFERRED", "ref": "derived:temp_c"}}}]}


SUBJECT_EXEC = {"agent": "agent:r1", "task": "task:r1", "runtime": "runtime:r1", "tool": ("tool:r1:Bash",)}
HOT = {"name": "hot", "model": "Server", "where": [["status", "in", ["hot", "critical"]]]}


def cases(dc):
    P = dc.PURPOSES
    ex, cr = P["execution_control"], P["context_runtime"]
    nodefault = ex.with_(version="purpose-execution-guard-nodefault", default_decision=())
    fresh = {"progress_state": ("NO_STALL_DETECTED", "INFERRED", NOW - MIN)}
    stale_opt = {**fresh, "tool_execution_health": ("RECOVERED_FAILURES", "INFERRED", NOW - 20 * MIN)}
    stale_req = {**fresh, "rate_limit_state": ("AVAILABLE", "INFERRED", NOW - 20 * MIN)}
    caps_all = {"human_reviewer": True, "retry_budget": True}
    B = dc.DecisionContextBuilder
    out = [
        ("exec_complete", ex, B([_sensor(dc, **fresh)]).build(ex, SUBJECT_EXEC, now_ms=NOW, capabilities=caps_all)),
        ("exec_incomplete_escalate", ex, B([_sensor(dc)]).build(ex, SUBJECT_EXEC, now_ms=NOW, capabilities=caps_all)),
        ("exec_incomplete_stop", ex, B([_sensor(dc)]).build(ex, SUBJECT_EXEC, now_ms=NOW, capabilities={})),
        ("exec_stale_optional", ex, B([_sensor(dc, **stale_opt)]).build(ex, SUBJECT_EXEC, now_ms=NOW,
                                                                         capabilities=caps_all)),
        ("exec_stale_required", ex, B([_sensor(dc, **stale_req)]).build(ex, SUBJECT_EXEC, now_ms=NOW,
                                                                         capabilities=caps_all)),
        ("exec_no_default", nodefault, B([_sensor(dc)], purposes={nodefault.name: nodefault}).build(
            nodefault, SUBJECT_EXEC, now_ms=NOW, capabilities=caps_all)),
        ("cr_complete", cr, B([_ms(dc)]).build(cr, {"session": "session:s1"}, now_ms=NOW)),
        ("cr_query_stale", cr, B([_ms(dc), _World()]).build(cr, {"session": "session:s1"}, now_ms=NOW,
                                                             queries=[dict(HOT, source="ms_world")])),
    ]
    rows = []
    for name, purpose, ctx in out:
        v = ctx.validity
        stale = sorted([s.key for s in ctx.states if s.status == "STALE"] +
                       [f"{q.name}/{r.id}.{p}" for q in ctx.core.queries for r in q.rows for p, _, st in r.props
                        if st == "STALE"])
        rows.append({"name": name, "record": ctx.to_dict(), "purpose": json.loads(json.dumps(dataclasses.asdict(purpose))),
                     "dc_projection": {"id": ctx.id, "complete": v.complete, "missing_required": sorted(v.missing_required),
                                       "stale_keys": stale, "default_action": ctx.default_action,
                                       "default_decision": list(purpose.default_decision),
                                       "actions": list(ctx.core.actions)}})
    return rows


def build() -> "list | None":
    dc = load_dc()
    if dc is None:
        return None
    return json.loads(json.dumps(cases(dc), ensure_ascii=False))


def main() -> int:
    rows = build()
    if rows is None:
        print("DC 를 찾지 못했다(DC_REPO 또는 옆 디렉터리)")
        return 2
    if "--check" in sys.argv:
        same = json.loads(OUT.read_text(encoding="utf-8")) == rows
        print("같다" if same else "다르다 -- DC 빌더 출력이 바뀌었다")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for r in rows:
        p = r["dc_projection"]
        print(f"{r['name']:<26} {p['id']}  complete={p['complete']!s:<5} missing={p['missing_required']} "
              f"stale={p['stale_keys']} default={p['default_action']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
