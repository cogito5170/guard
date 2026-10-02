"""DC 결정 문맥(데이터) → DCView (CMD-G2). 고정 파일은 DC 의 실제 빌더가 지었다(`eval/dc_fixtures.py`)."""
import copy
import json
import pathlib
import unittest

from action.forms import ActionIntent

from guard import (ALLOW, DENY, SAFE_ACTION, ActionSpec, Entity, GuardModel, Prop, StateView, ViewError,
                   dcview_from_dc, evaluate)
from eval import dc_fixtures

FIX = json.loads((pathlib.Path(__file__).parent / "fixtures" / "dc_contexts.json").read_text(encoding="utf-8"))
CASES = {c["name"]: c for c in FIX}

# 실행기 행동: 목적 단위 행동(겨냥 없음) + 런타임이 넘기는 겨냥 있는 행동 둘. KEEP(CR 안의 맥락 결정)은 실행기 행동이 아니다(BD-100)
MODEL = GuardModel({s.name: s for s in [
    ActionSpec("CONTINUE", None, risk="local"), ActionSpec("RETRY", None, risk="external"),
    ActionSpec("ESCALATE", None, risk="external"), ActionSpec("STOP", None, risk="local"),
    ActionSpec("reboot", "Server", preconditions=(("status", "==", "critical"),), risk="irreversible"),
    ActionSpec("throttle", "Server", {"level": {"type": "integer", "min": 1, "max": 3}},
               (("status", "in", ["hot", "critical"]),), "local"),
]}, frozenset({"RETRY", "ESCALATE", "reboot"}))
STATE = StateView({"srv1": Entity("Server", 3, {"status": Prop("critical", False, 1.0)})})
OFFERS = {"reboot": ["srv1"], "throttle": ["srv1"]}
SEEN = {"srv1": 3}


def view(name, **kw):
    c = CASES[name]
    return dcview_from_dc(c["record"], c["purpose"], **kw)


def intent(v, action, target=None, args=None):
    return ActionIntent(v.dc_id, "ms-cr@cr-3", action, target, args or {}, "시험", (), "llm")


class FromRealBuilder(unittest.TestCase):
    def test_cases_cover_the_asked_shapes(self):
        p = {n: c["dc_projection"] for n, c in CASES.items()}
        self.assertTrue(any(x["complete"] and not x["stale_keys"] for x in p.values()))           # 완전
        self.assertTrue(any(not x["complete"] for x in p.values()))                              # 불완전
        self.assertTrue(any(x["complete"] and x["stale_keys"] for x in p.values()))               # 낡은 키(필수 아님)
        self.assertTrue(any(x["default_action"] is None for x in p.values()))                     # 기본 결정 없음
        self.assertTrue(any(x["default_action"] is not None for x in p.values()))                 # 기본 결정 있음

    def test_view_matches_dc_projection(self):
        for name, c in CASES.items():
            p, v = c["dc_projection"], view(name)
            self.assertEqual(v.dc_id, p["id"], name)
            self.assertEqual(v.complete, p["complete"], name)
            self.assertEqual(list(v.missing_required), p["missing_required"], name)
            self.assertEqual(list(v.stale_keys), p["stale_keys"], name)
            self.assertEqual(v.default_action, p["default_action"], name)
            self.assertEqual(list(v.default_decision), p["default_decision"], name)
            self.assertEqual(list(v.required_keys), p["required_keys"], name)
            self.assertEqual(v.offers, {a: [None] for a in p["actions"]}, name)
            self.assertEqual(v.seen, {}, name)

    def test_core_dict_gives_the_same_view(self):
        for name, c in CASES.items():
            core_dict = {"id": c["dc_projection"]["id"], **c["record"]["core"]}
            self.assertEqual(dcview_from_dc(core_dict, c["purpose"]), view(name), name)

    def test_runtime_offers_and_seen_are_merged(self):
        v = view("exec_complete", offers=OFFERS, seen=SEEN)
        self.assertEqual(v.offers["reboot"], ["srv1"])
        self.assertEqual(v.offers["STOP"], [None])
        self.assertEqual(v.seen, SEEN)


class Refuses(unittest.TestCase):
    def test_tampered_record(self):
        c = copy.deepcopy(CASES["exec_incomplete_escalate"])
        c["record"]["core"]["states"]["task.progress_state"] = ["NO_STALL_DETECTED", "INFERRED"]   # 모름을 앎으로
        with self.assertRaises(ViewError):
            dcview_from_dc(c["record"], c["purpose"])

    def test_purpose_must_match(self):
        c = CASES["exec_complete"]
        with self.assertRaises(ViewError):
            dcview_from_dc(c["record"], {**c["purpose"], "version": "purpose-execution-2"})
        with self.assertRaises(ViewError):
            dcview_from_dc(c["record"], CASES["cr_complete"]["purpose"])
        with self.assertRaises(ViewError):
            dcview_from_dc(c["record"], {**c["purpose"], "owner": "me"})

    def test_shape(self):
        c = CASES["exec_complete"]
        core = {"id": c["dc_projection"]["id"], **c["record"]["core"]}
        for bad in ({**core, "extra": 1}, {k: v for k, v in core.items() if k != "actions"},
                    {**core, "id": "x-1"}, {"core": core}, [core], {**core, "states": {"a.b": "X"}}):
            with self.assertRaises(ViewError, msg=str(bad)[:60]):
                dcview_from_dc(bad, c["purpose"])

    def test_required_ref_missing_from_core_is_incomplete(self):
        c = CASES["exec_complete"]
        core = {"id": c["dc_projection"]["id"], **c["record"]["core"]}
        core["states"] = {k: v for k, v in core["states"].items() if k != "task.progress_state"}
        v = dcview_from_dc(core, c["purpose"])
        self.assertEqual((v.complete, v.missing_required), (False, ("task.progress_state",)))

    def test_tailed_key_matches_its_role(self):
        # "tool[Bash].tool_execution_health" 는 역할 tool 의 키다. 목적이 그것을 필수로 부르면 STALE 은 불완전
        c = CASES["exec_stale_optional"]
        refs = [{**r, "required": True} if r["name"] == "tool_execution_health" else r for r in c["purpose"]["refs"]]
        v = dcview_from_dc(c["record"], {**c["purpose"], "refs": refs})
        self.assertEqual((v.complete, v.missing_required), (False, ("tool[Bash].tool_execution_health",)))

    def test_ref_without_required_field_is_required(self):
        c = CASES["exec_incomplete_escalate"]                  # DC StateRef.required 기본값은 참이다
        refs = [{k: x for k, x in r.items() if k != "required"} for r in c["purpose"]["refs"]]
        v = dcview_from_dc(c["record"], {**c["purpose"], "refs": refs})
        self.assertFalse(v.complete)
        self.assertIn("task.quality_state", v.missing_required)        # 원래 required=False 였던 키
        self.assertNotIn("agent.resource_state", v.missing_required)   # NOT_APPLICABLE 은 필수여도 빠진 것이 아니다

    def test_default_action_outside_candidates(self):
        c = CASES["exec_incomplete_stop"]                      # DC 는 STOP 을 골랐다
        with self.assertRaises(ViewError):
            dcview_from_dc(c["record"], {**c["purpose"], "default_decision": ["ESCALATE"]})

    def test_unrequired_unusable_does_not_make_incomplete(self):
        c = CASES["exec_complete"]
        core = {"id": c["dc_projection"]["id"], **c["record"]["core"]}
        core["states"] = {**core["states"], "agent.resource_state": [None, "UNKNOWN"]}     # required=False
        self.assertTrue(dcview_from_dc(core, c["purpose"]).complete)


class DStandsOnRealContexts(unittest.TestCase):
    """CMD-G2 끝난 기준 2: D 가 실제 문맥 위에서 선다."""
    EXPECT = {   # 위험 행동(reboot, irreversible) 하나에 대한 판정
        "exec_complete": (ALLOW, "0", None),
        "exec_incomplete_escalate": (SAFE_ACTION, "D", "ESCALATE"),
        "exec_incomplete_stop": (SAFE_ACTION, "D", "STOP"),
        "exec_stale_optional": (ALLOW, "0", None),               # 낡은 키는 필수가 아니고 의도가 안 썼다(BD-103)
        "exec_stale_required": (SAFE_ACTION, "D", "ESCALATE"),
        "exec_no_default": (DENY, "D", None),
        "cr_complete": (ALLOW, "0", None),
        "cr_query_stale": (ALLOW, "0", None),                    # 질의 hot 을 의도가 안 썼다
    }

    def test_risky_action(self):
        self.assertEqual(set(self.EXPECT), set(CASES))
        for name, want in self.EXPECT.items():
            v = view(name, offers=OFFERS, seen=SEEN)
            _, r = evaluate(intent(v, "reboot", "srv1"), v, STATE, MODEL)
            self.assertEqual((r.verdict, r.rule, r.safe_action), want, name)
            if r.verdict == SAFE_ACTION:
                self.assertIn(r.safe_action, v.default_decision)
                self.assertIn(r.safe_action, v.offers)            # DC 가 능력으로 고른 것 = 가능한 행동

    def test_used_stale_keys_trigger_D(self):
        """BD-103 판정표의 둘째 반: 의도가 낡은 키를 썼으면 SAFE_ACTION."""
        for name, used, want in [("exec_stale_optional", ("tool[Bash].tool_execution_health",), "ESCALATE"),
                                 ("cr_query_stale", ("query:hot",), None),
                                 ("cr_query_stale", ("hot/srv07.fan_rpm",), None)]:
            v = view(name, offers=OFFERS, seen=SEEN)
            it = ActionIntent(v.dc_id, "ms-cr@cr-3", "reboot", "srv1", {}, "시험", used, "llm")
            _, r = evaluate(it, v, STATE, MODEL)
            if want is None:                      # 기본 KEEP 은 실행기 행동이 아니다 → DENY(D) (BD-104)
                self.assertEqual((r.verdict, r.rule, r.safe_action), (DENY, "D", None), (name, used))
                self.assertIn("실행기 행동이 아니다", r.reasons[-1])
            else:
                self.assertEqual((r.verdict, r.rule, r.safe_action), (SAFE_ACTION, "D", want), (name, used))
        v = view("cr_query_stale", offers=OFFERS, seen=SEEN)                 # 다른 질의 · 신선한 키를 쓴 것은 걸지 않는다
        for used in (("query:cold",), ("session.context_pressure",)):
            it = ActionIntent(v.dc_id, "ms-cr@cr-3", "reboot", "srv1", {}, "시험", used, "llm")
            self.assertEqual(evaluate(it, v, STATE, MODEL)[1].verdict, ALLOW, used)

    def test_enforce_agrees_on_real_contexts(self):
        """CMD-G6: DC 실제 빌더 문맥 8 개 × 행동 셋 × used_keys 넷에서 shadow · enforce 판정이 같다(mode 칸만 다름)."""
        n = 0
        for name in CASES:
            v = view(name, offers=OFFERS, seen=SEEN)
            for action, target, args in (("reboot", "srv1", {}), ("throttle", "srv1", {"level": 1}), ("ESCALATE", None, {})):
                for used in ((), ("query:hot",), ("tool[Bash].tool_execution_health",), ("runtime.rate_limit_state",)):
                    it = ActionIntent(v.dc_id, "ms-cr@cr-3", action, target, args, "시험", used, "llm")
                    s = evaluate(it, v, STATE, MODEL)[1].to_dict()
                    e = evaluate(it, v, STATE, MODEL, mode="enforce")[1].to_dict()
                    self.assertEqual((s.pop("mode"), e.pop("mode")), ("shadow", "enforce"))
                    s.pop("guard_id"), e.pop("guard_id")
                    self.assertEqual(s, e, (name, action, used))
                    n += 1
        self.assertEqual(n, 8 * 3 * 4)

    def test_reasons_name_the_missing_keys(self):
        v = view("exec_incomplete_escalate", offers=OFFERS, seen=SEEN)
        _, r = evaluate(intent(v, "reboot", "srv1"), v, STATE, MODEL)
        self.assertIn("task.progress_state", r.reasons[0])

    def test_local_action_passes_everywhere(self):
        for name in CASES:
            v = view(name, offers=OFFERS, seen=SEEN)
            _, r = evaluate(intent(v, "throttle", "srv1", {"level": 1}), v, STATE, MODEL)
            self.assertEqual(r.verdict, ALLOW, name)

    def test_purpose_actions(self):
        v = view("exec_incomplete_escalate")
        self.assertEqual(evaluate(intent(v, "ESCALATE"), v, STATE, MODEL)[1].verdict, ALLOW)    # 안전 기본 후보는 막지 않는다
        r = evaluate(intent(v, "RETRY"), v, STATE, MODEL)[1]                                     # 위험(external), 후보 밖
        self.assertEqual((r.verdict, r.safe_action), (SAFE_ACTION, "ESCALATE"))
        v2 = view("exec_incomplete_stop")                                                       # retry_budget 이 없다
        self.assertEqual(evaluate(intent(v2, "RETRY"), v2, STATE, MODEL)[1].rule, "A1")

    def test_intent_must_be_for_this_context(self):
        a, b = view("exec_complete", offers=OFFERS, seen=SEEN), view("cr_complete", offers=OFFERS, seen=SEEN)
        self.assertEqual(evaluate(intent(a, "reboot", "srv1"), b, STATE, MODEL)[1].rule, "A0")


@unittest.skipIf(dc_fixtures.find_dc() is None, "DC 저장소가 옆에 없다(DC_REPO)")
class Drift(unittest.TestCase):
    def test_fixtures_are_what_dc_builds_now(self):
        self.assertEqual(dc_fixtures.build(), FIX)
