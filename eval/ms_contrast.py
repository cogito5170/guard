"""대조 시험 -- MS `ms/arbiter.py` 와 Guard(`evaluate`)가 같은 입력에서 같은 판정을 내나 (baseline#7 CMD-G1 끝난 기준 1).

    python3 eval/ms_contrast.py          # MS 를 옆 디렉터리(또는 MS_REPO)에서 찾는다. 다른 판정이 있으면 표로 찍고 1 로 끝난다

Guard 패키지는 MS 를 import 하지 않는다. 이 파일(시험 · 평가)만 MS 를 읽기 전용으로 부른다.

같은 입력을 짓는 법
- 세계: MS `ms/examples/datacenter.json` + 텔레메트리(MS 시험의 `world()` 와 같다). MS 의 맥락 정책으로 맥락을 짓는다.
- MS 맥락 → DCView(offers · seen · decisions · handles. complete=True · 낡은 키 없음 -- MS 맥락에는 완전성 칸이 없다)
- MS State Manager → StateView(실체마다 판 · 속성 값 · `is_stale`) -- 맥락을 지은 **뒤**, 판정 직전에 읽는다
- MS 도구 정의 → action ActionModel → GuardModel(`from_action_model`, CMD-G5). ToolRegistry 에서 바로 지은 것과 같은지도 센다
- MS Proposal → ActionIntent(dc_id 고정, policy `ms-cr@cr-3` (BD-97 Q2), author_kind `llm`)
- A8: Guard 가 ALLOW 한 뒤 `repeat_key` 를 StateView.allowed 에 더한다(MS 는 Arbiter 안에 둔다)

비교는 (verdict, rule) 이다. 까닭 글은 비교하지 않는다(Guard 는 걸린 규칙을 모두 적고 MS 는 첫 것만 적는다).
범위 밖: `none`(NOOP) · `retrieve` 는 의도가 되지 않는다(BD-97) -- 세기만 한다.
"""
from __future__ import annotations

import itertools
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from action.forms import ActionIntent, ContractError  # noqa: E402

from guard import ALLOW, ActionSpec, DCView, Entity, GuardModel, Prop, StateView, evaluate, repeat_key  # noqa: E402

DC_ID = "dc-ms-contrast"
POLICY = "ms-cr@cr-3"


def find_ms() -> "pathlib.Path | None":
    for p in filter(None, [os.environ.get("MS_REPO"), ROOT.parent / "MS", ROOT.parent / "ms",
                           ROOT.parent / "cogito5170" / "ms"]):
        p = pathlib.Path(p)
        if (p / "ms" / "arbiter.py").exists():
            return p.resolve()
    return None


def load_ms():
    p = find_ms()
    if p is None:
        return None
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
    import ms
    return ms


# ── 어댑터 (MS 꼴 → Guard 입력 꼴) ─────────────────────────────────────────────

def dc_from_ms(ctx) -> DCView:
    return DCView(DC_ID, {o["tool"]: list(o["targets"]) for o in ctx.offers}, dict(ctx.seen), dict(ctx.decisions),
                  {h: list(v["ids"]) for h, v in ctx.handles.items()})


def state_from_ms(m, allowed) -> "StateView | None":
    if m is None:
        return None
    ents = {}
    for nid, n in m.graph.nodes.items():
        ents[nid] = Entity(n.model, n.version, {p: Prop(v.value, m.is_stale(nid, p), m.age(nid, p))
                                               for p, v in n.props.items()})
    return StateView(ents, frozenset(allowed))


def model_from_ms(reg, grants) -> GuardModel:
    """MS ToolRegistry 에서 바로 지은 GuardModel(G1 의 길). 대조에서는 아래 ActionModel 길과 같음을 확인하는 데만 쓴다."""
    specs = {t.name: ActionSpec(t.name, t.target_model, dict(t.params), tuple(t.preconditions), t.risk)
             for t in reg.tools.values()}
    return GuardModel(specs, frozenset(grants))


def model_from_action(tools, grants) -> GuardModel:
    """CMD-G5 의 길: MS 도구 정의(JSON) → action `ActionSpec.from_tool` → `ActionModel` → `GuardModel.from_action_model`.
    MS 의 내장 `retrieve` 는 도구 정의에 없다(의도가 되지 않으므로 Guard 도 A0 로 막는다, BD-97)."""
    from action.spec import ActionModel, ActionSpec as SpecA
    am = ActionModel("ms-datacenter@contrast", tuple(SpecA.from_tool(t, "1") for t in tools))
    return GuardModel.from_action_model(am, grants=grants)


def intent_from_ms(p) -> "ActionIntent | None":
    """None = 의도가 될 수 없다(꼴이 틀림 -- MS A0 와 맞대 본다)."""
    if p.error or not isinstance(p.tool, str):
        return None
    try:
        return ActionIntent(DC_ID, POLICY, p.tool, p.target, p.args, p.rationale or "", (), "llm")
    except ContractError:
        return None


# ── 세계 · 경우 ────────────────────────────────────────────────────────────────

class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def world(ms, budget, grants):
    msroot = find_ms()
    spec = json.loads((msroot / "ms" / "examples" / "datacenter.json").read_text(encoding="utf-8"))
    clock = Clock(spec["now"])
    m = ms.StateManager.from_spec(spec, clock=clock)
    for line in (msroot / "ms" / "examples" / "datacenter_telemetry.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            m.ingest(json.loads(line))
    reg = ms.ToolRegistry(spec["tools"])
    pol = ms.ContextPolicy(budget_chars=budget, summarize_min=3)
    ctx = ms.Pipeline(m, reg, ms.ScriptedLLM([]), pol).context("t", spec["queries"])
    return spec, m, reg, ctx, clock, ms.Arbiter(reg, grants, clock=clock)


def _perturb(ms, kind, m, clock):
    """맥락을 지은 **뒤** 세계를 바꾼다(지금 상태가 결정이 본 것과 달라진다)."""
    if kind == "cooled_srv07":           # A5: 판이 오른다
        m.ingest(ms.Telemetry("bmc", "srv07", "cpu_temp", 70, ts=clock.t - 0.5))
    elif kind == "heated_srv01":         # A5: 본 개체가 바뀐다
        m.ingest(ms.Telemetry("bmc", "srv01", "cpu_temp", 95, ts=clock.t - 0.5))
    elif kind == "stale_120s":           # A6: ttl 60 을 넘긴다
        clock.t += 120
    elif kind == "aged_30s":
        clock.t += 30
    elif kind == "no_state":             # E: 지금 상태를 읽지 못한다
        return None
    return m


ARGS = [{}, {"level": 1}, {"level": 2}, {"level": 3}, {"level": 9}, {"level": 0}, {"level": 2.0}, {"level": 2.5},
        {"level": "2"}, {"level": True}, {"note": "팬"}, {"note": 3}, {"level": 1, "x": 1}, {"note": "팬", "level": 1}]
GRANTS = [(), ("reboot",), ("reboot", "open_ticket")]
BUDGETS = [1500, 100000]
PERTURB = ["none", "cooled_srv07", "heated_srv01", "stale_120s", "aged_30s", "no_state"]


def proposals(ms, spec, ctx):
    tools = [t["name"] for t in spec["tools"]] + ["format_disk", "none", "retrieve"]
    targets = [e["id"] for e in spec["entities"]] + ["srv99"] + sorted(ctx.handles) + ["h99"]
    out = [ms.parse_proposal("재부팅하세요"), ms.parse_proposal('{"tool": 3}')]
    for tool, target, args in itertools.product(tools, targets, ARGS):
        out.append(ms.parse_proposal(json.dumps({"tool": tool, "target": target, "args": args,
                                                 "rationale": "대조"}, ensure_ascii=False)))
    return out


def run() -> dict:
    ms = load_ms()
    if ms is None:
        return {"ms": None}
    rep = {"ms": str(find_ms()), "cases": 0, "compared": 0, "matched": 0, "out_of_scope": {}, "by_rule": {},
           "diffs": []}
    for budget, grants, kind in itertools.product(BUDGETS, GRANTS, PERTURB):
        spec, m, reg, ctx, clock, arb = world(ms, budget, grants)
        dc, model = dc_from_ms(ctx), model_from_action(spec["tools"], grants)
        hand = model_from_ms(reg, grants)                # 두 길이 같은 행동 명세를 내야 한다(retrieve 만 빼고)
        if {k: v for k, v in hand.specs.items() if k != "retrieve"} != model.specs or hand.grants != model.grants:
            rep["model_mismatch"] = rep.get("model_mismatch", 0) + 1
        mm = _perturb(ms, kind, m, clock)
        allowed: set = set()
        for p in proposals(ms, spec, ctx) * 2:          # 두 번 -- 둘째 바퀴에서 되풀이(A8)가 걸린다
            rep["cases"] += 1
            d = arb.decide(p, ctx, mm)
            if p.tool in ("none", "retrieve") and not p.error:
                rep["out_of_scope"][p.tool] = rep["out_of_scope"].get(p.tool, 0) + 1
                continue
            it = intent_from_ms(p)
            if it is None:
                g = ("DENY", "A0")
            else:
                sv = state_from_ms(mm, allowed)
                _, gr = evaluate(it, dc, sv, model)
                _, ge = evaluate(it, dc, sv, model, mode="enforce")      # CMD-G6: 판정은 모드와 무관해야 한다
                a, b = gr.to_dict(), ge.to_dict()
                if (a.pop("mode"), b.pop("mode")) != ("shadow", "enforce") or \
                        {k: v for k, v in a.items() if k != "guard_id"} != {k: v for k, v in b.items() if k != "guard_id"}:
                    rep["mode_diffs"] = rep.get("mode_diffs", 0) + 1
                g = (gr.verdict, gr.rule)
                if gr.verdict == ALLOW:
                    allowed.add(repeat_key(it, mm.graph.nodes[it.target].version))
            rep["compared"] += 1
            want = (d.verdict, d.rule)
            rep["by_rule"][d.rule] = rep["by_rule"].get(d.rule, 0) + 1
            if g == want:
                rep["matched"] += 1
            else:
                rep["diffs"].append({"budget": budget, "grants": list(grants), "perturb": kind,
                                     "proposal": p.to_dict(), "ms": list(want), "guard": list(g)})
    return rep


def main() -> int:
    rep = run()
    if rep["ms"] is None:
        print("MS 를 찾지 못했다(MS_REPO 또는 옆 디렉터리) -- 대조하지 않는다")
        return 2
    print(f"MS: {rep['ms']}")
    print(f"경우 {rep['cases']} · 비교 {rep['compared']} · 같음 {rep['matched']} · 다름 {len(rep['diffs'])} · "
          f"범위 밖 {rep['out_of_scope']} · 모델 다름 {rep.get('model_mismatch', 0)} · 모드 다름 {rep.get('mode_diffs', 0)}")
    print("MS 판정 규칙별 수: " + " · ".join(f"{k} {v}" for k, v in sorted(rep["by_rule"].items())))
    for x in rep["diffs"][:40]:
        print(json.dumps(x, ensure_ascii=False))
    return 1 if rep["diffs"] or rep.get("model_mismatch") or rep.get("mode_diffs") else 0


if __name__ == "__main__":
    sys.exit(main())
