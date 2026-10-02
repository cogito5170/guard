import dataclasses
import itertools
import unittest

from guard import ALLOW, DENY, SAFE_ACTION, Entity, Prop, StateView, evaluate, guard, repeat_key
from tests.fixture import dc, intent, model, state


def _same(r):
    """모드 말고 전부(id 는 mode 칸이 들어가므로 다르다)."""
    d = r.to_dict()
    return {k: v for k, v in d.items() if k not in ("mode", "guard_id")}


def g(it=None, d=None, s=None, m=None):
    return guard(it or intent(), d or dc(), s or state(), m or model())


class GuardRules(unittest.TestCase):
    def test_allow(self):
        r = g()
        self.assertEqual((r.verdict, r.rule, r.mode, r.safe_action), (ALLOW, "0", "shadow", None))
        self.assertEqual(r.state_refs, ("srv1.status", "srv1@4"))

    def test_A5_changed_after_context(self):
        s = state(srv1=Entity("Server", 5, state().entities["srv1"].props))
        r = g(s=s)
        self.assertEqual((r.verdict, r.rule), (DENY, "A5"))
        self.assertIn("srv1@5", r.state_refs)

    def test_A5_gone_now(self):
        s = StateView({k: v for k, v in state().entities.items() if k != "srv1"})
        self.assertEqual(g(s=s).rule, "A5")

    def test_A5_not_seen_by_decision(self):
        # VALIDATE 를 거치지 않고 불러도(지금 상태에는 있지만 결정이 판을 보지 않은 실체) 예외가 아니라 A5
        r = g(intent("inspect", "rack", {}))
        self.assertEqual((r.verdict, r.rule), (DENY, "A5"))

    def test_A6_targetless_with_preconditions(self):
        m = model()
        halt = dataclasses.replace(m.specs["escalate"], name="halt", risk="local", preconditions=(("status", "==", "x"),))
        m2 = dataclasses.replace(m, specs={**m.specs, "halt": halt})
        r = g(intent("halt", None, {}), d=dc(offers={**dc().offers, "halt": [None]}), m=m2)
        self.assertEqual((r.verdict, r.rule), (DENY, "A6"))
        self.assertEqual(g(intent("escalate", None, {})).verdict, ALLOW)

    def test_A6_stale_or_missing(self):
        self.assertEqual(g(intent(target="srv3")).rule, "A6")                    # status 가 낡았다
        s = state(srv1=Entity("Server", 4, {"fan": Prop("failed", False)}))      # status 가 없다
        self.assertEqual(g(s=s).rule, "A6")

    def test_A6_false_now(self):
        s = state(srv1=Entity("Server", 4, {"status": Prop("normal", False)}))
        r = g(s=s)
        self.assertEqual(r.rule, "A6")
        self.assertIn("거짓", r.reasons[0])

    def test_A6_wrong_model(self):
        s = state(srv1=Entity("Rack", 4, {"status": Prop("hot", False)}))
        self.assertEqual(g(s=s).rule, "A6")

    def test_A7_needs_grant(self):
        self.assertEqual(g(intent("reboot", "srv1", {}), m=model(grants=())).rule, "A7")
        self.assertEqual(g(intent("open_ticket", "srv1", {"note": "팬"}), m=model(grants=("reboot",))).rule, "A7")
        self.assertEqual(g(intent("reboot", "srv1", {})).verdict, ALLOW)
        self.assertEqual(g(intent("throttle"), m=model(grants=())).verdict, ALLOW)     # local 은 허가가 없어도

    def test_A8_repeat(self):
        it = intent()
        s = state(allowed={repeat_key(it, 4)})
        self.assertEqual(g(it, s=s).rule, "A8")
        self.assertEqual(g(intent(rationale="다른 까닭"), s=s).rule, "A8")       # 까닭만 바꾼 되풀이도
        self.assertEqual(g(it, s=state(allowed={repeat_key(it, 3)})).verdict, ALLOW)   # 다른 판이면 되풀이가 아니다

    def test_all_failing_rules_are_reasons(self):
        s = state(srv1=Entity("Server", 5, {"status": Prop("normal", False)}))
        r = g(intent("reboot", "srv1", {}), s=s, m=model(grants=()))
        self.assertEqual(r.rule, "A5")                                             # 첫 것은 MS 의 순서
        self.assertEqual([x[:4] for x in r.reasons], ["[A5]", "[A6]", "[A7]"])

    def test_exception_fails_closed(self):
        r = guard(intent(), dc(), None, model())
        self.assertEqual((r.verdict, r.rule), (DENY, "E"))
        r = guard("의도 아님", dc(), state(), model())
        self.assertEqual((r.verdict, r.rule), (DENY, "E"))

    def test_enforce_is_accepted_and_only_the_mode_differs(self):
        """CMD-G6 · BD-114: enforce 를 받는다. 판정은 모드와 무관하다 -- mode 칸만 다르다."""
        for it, d in [(intent(), dc()), (intent(target="srv3"), dc()), (intent("reboot", "srv1", {}), dc(complete=False))]:
            s, e = guard(it, d, state(), model()), guard(it, d, state(), model(), mode="enforce")
            self.assertEqual((s.mode, e.mode), ("shadow", "enforce"))
            self.assertEqual(_same(s), _same(e))

    def test_exception_is_deny_in_both_modes(self):
        for mode in ("shadow", "enforce"):
            r = guard(intent(), dc(), None, model(), mode=mode)
            self.assertEqual((r.verdict, r.rule, r.mode), (DENY, "E", mode))
            self.assertEqual(evaluate(intent(), None, state(), model(), mode=mode)[1].rule, "E")

    def test_unknown_mode_is_refused(self):
        for mode in ("loud", "Enforce", None, ""):
            with self.assertRaises(ValueError, msg=mode):
                guard(intent(), dc(), state(), model(), mode=mode)
            with self.assertRaises(ValueError, msg=mode):
                evaluate(intent(), dc(), state(), model(), mode=mode)

    def test_pure(self):
        a, b = g(), g()
        self.assertEqual(a, b)
        self.assertEqual(a.id, b.id)


class IncompleteDC(unittest.TestCase):
    """D -- DC 가 불완전하거나 낡은 키가 있으면 위험 행동은 막는다(DATA_FLOW §6.5)."""
    reboot = staticmethod(lambda: intent("reboot", "srv1", {}))

    def test_incomplete_risky_gets_safe_action(self):
        r = g(self.reboot(), d=dc(complete=False))
        self.assertEqual((r.verdict, r.rule, r.safe_action), (SAFE_ACTION, "D", "escalate"))

    def test_stale_key_scope_is_required_or_used(self):
        """BD-103: 낡은 키 가운데 필수 키 ∪ 의도가 쓴 키만 본다."""
        ticket = lambda used: intent("open_ticket", "srv1", {"note": "팬"}, used_keys=used)  # noqa: E731
        self.assertEqual(g(ticket(("status",)), d=dc(stale_keys=("fan",))).verdict, ALLOW)          # 안 쓴 · 필수 아님
        r = g(ticket(("status", "fan")), d=dc(stale_keys=("fan",)))                                  # 썼다
        self.assertEqual((r.verdict, r.rule), (SAFE_ACTION, "D"))
        self.assertIn("fan", r.reasons[0])
        r = g(ticket(("status",)), d=dc(stale_keys=("fan",), required_keys=("fan",)))                # 필수다
        self.assertEqual((r.verdict, r.rule), (SAFE_ACTION, "D"))

    def test_query_scope(self):
        """`query:<이름>` 은 그 질의의 행 속성 전부(`"<이름>/<행>.<속성>"`)."""
        d = dc(stale_keys=("hot/srv1.fan_rpm",))
        boot = lambda used: intent("reboot", "srv1", {}, used_keys=used)  # noqa: E731
        self.assertEqual(g(boot(("query:hot",)), d=d).verdict, SAFE_ACTION)
        self.assertEqual(g(boot(("hot/srv1.fan_rpm",)), d=d).verdict, SAFE_ACTION)       # 속성 하나를 콕 집어 써도
        for used in (("query:cold",), ("query:ho",), ("hot",), ("status",)):
            self.assertEqual(g(boot(used), d=d).verdict, ALLOW, used)

    def test_no_default_action_is_deny(self):
        r = g(self.reboot(), d=dc(complete=False, default_action=None))
        self.assertEqual((r.verdict, r.rule, r.safe_action), (DENY, "D", None))

    def test_safe_action_must_be_an_executor_action(self):
        # BD-104: 기본 결정이 ActionSpec 에 없는 행동(예: CR 의 KEEP)이면 갈아 끼우지 않고 DENY(D)
        d = dc(complete=False, default_decision=("KEEP",), default_action="KEEP")
        r = g(self.reboot(), d=d)
        self.assertEqual((r.verdict, r.rule, r.safe_action), (DENY, "D", None))
        self.assertIn("실행기 행동이 아니다", r.reasons[-1])
        d = dc(complete=False, default_decision=("stop", "escalate"), default_action="stop")    # 후보 안이지만 ActionSpec 없음
        self.assertEqual(g(self.reboot(), d=d).verdict, DENY)

    def test_safe_action_only_from_default_decision(self):
        # DCView.check 를 거치지 않고 지은 문맥이라도 후보 밖의 기본 행동으로는 갈아 끼우지 않는다
        bad = dataclasses.replace(dc(complete=False), default_action="reboot")
        r = g(self.reboot(), d=bad)
        self.assertEqual((r.verdict, r.safe_action), (DENY, None))

    def test_not_risky_passes(self):
        self.assertEqual(g(d=dc(complete=False, stale_keys=("x",))).verdict, ALLOW)          # throttle 은 local
        self.assertEqual(g(intent("inspect", "srv2", {}), d=dc(complete=False)).verdict, ALLOW)
        r = g(d=dc(complete=False), m=model(risky=("local", "external", "irreversible")))     # 위험 등급은 Model 이 정한다
        self.assertEqual(r.rule, "D")

    def test_default_candidate_is_not_blocked(self):
        r = g(intent("escalate", None, {}), d=dc(complete=False))
        self.assertEqual(r.verdict, ALLOW)

    def test_complete_and_fresh_is_not_D(self):
        self.assertEqual(g(self.reboot()).verdict, ALLOW)

    def test_D_comes_first_and_others_are_kept(self):
        r = g(self.reboot(), d=dc(complete=False), m=model(grants=()))
        self.assertEqual(r.rule, "D")
        self.assertTrue(any(x.startswith("[A7]") for x in r.reasons))


class ClosesOnly(unittest.TestCase):
    """닫는 쪽으로만: 제약을 하나 더하면 ALLOW 가 아니던 것이 ALLOW 가 되지 않는다. ALLOW 는 VALIDATE 를 지나야만."""

    def cases(self):
        its = [intent(), intent(target="srv3"), intent(target="srv2"), intent(args={"level": 9}),
               intent("reboot", "srv1", {}), intent("open_ticket", "srv1", {"note": "팬"}), intent("escalate", None, {}),
               intent("inspect", "srv2", {}), intent(dc_id="dc-x"), intent("format_disk", "srv1", {})]
        dcs = [dc(), dc(complete=False), dc(stale_keys=("status",)), dc(default_action=None, complete=False)]
        models = [model(), model(grants=()), model(grants=("reboot",))]
        states = [state(), state(allowed={repeat_key(intent(), 4)}),
                  state(srv1=Entity("Server", 5, state().entities["srv1"].props))]
        return list(itertools.product(its, dcs, states, models))

    def tighten(self, d, s, m):
        yield d, s, dataclasses.replace(m, grants=frozenset())
        yield dataclasses.replace(d, complete=False), s, m
        yield dataclasses.replace(d, stale_keys=d.stale_keys + ("status",)), s, m                 # 의도가 쓴 키가 낡음
        yield dataclasses.replace(d, stale_keys=d.stale_keys + ("fan",), required_keys=("fan",)), s, m   # 필수 키가 낡음
        yield dataclasses.replace(d, offers={k: [] for k in d.offers}), s, m
        yield dataclasses.replace(d, seen={}), s, m
        stale = {k: Entity(e.model, e.version, {p: Prop(v.value, True, v.age) for p, v in e.props.items()})
                 for k, e in s.entities.items()}
        yield d, StateView(stale, s.allowed), m
        bumped = {k: Entity(e.model, e.version + 1, e.props) for k, e in s.entities.items()}
        yield d, StateView(bumped, s.allowed), m

    def test_tightening_never_opens(self):
        n = 0
        for it, d, s, m in self.cases():
            v0, r0 = evaluate(it, d, s, m)
            if r0.verdict == ALLOW:
                self.assertTrue(v0.ok)
            for d2, s2, m2 in self.tighten(d, s, m):
                _, r = evaluate(it, d2, s2, m2)
                n += 1
                if r0.verdict != ALLOW:
                    self.assertNotEqual(r.verdict, ALLOW, (it.action, it.target, r0.rule, r.reasons))
                if r.verdict == SAFE_ACTION:
                    self.assertIn(r.safe_action, d2.default_decision)
        self.assertGreater(n, 2500)

    def test_shadow_and_enforce_agree_everywhere(self):
        """끝난 기준 1(전수): 닫힘 성질의 모든 경우와 그 조인 것에서 두 모드의 판정이 같다."""
        n = 0
        for it, d, s, m in self.cases():
            for d2, s2, m2 in [(d, s, m), *self.tighten(d, s, m)]:
                vs, rs = evaluate(it, d2, s2, m2)
                ve, re_ = evaluate(it, d2, s2, m2, mode="enforce")
                self.assertEqual(vs, ve)                       # VALIDATE 에는 모드가 없다
                self.assertEqual((rs.mode, re_.mode), ("shadow", "enforce"))
                self.assertEqual(_same(rs), _same(re_), (it.action, it.target, rs.rule))
                n += 1
        self.assertGreater(n, 3000)

    def test_validation_failure_is_never_allowed(self):
        for it, d, s, m in self.cases():
            v, r = evaluate(it, d, s, m)
            if not v.ok:
                self.assertEqual((r.verdict, r.rule), (DENY, v.rule))
                self.assertEqual(r.state_refs, ())
