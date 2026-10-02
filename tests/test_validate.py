import unittest

from guard import validate
from tests.fixture import dc, intent, model


class ValidateRules(unittest.TestCase):
    def v(self, it, d=None, m=None):
        return validate(it, d or dc(), m or model())

    def test_ok(self):
        r = self.v(intent())
        self.assertEqual((r.ok, r.rule), (True, "0"))
        self.assertEqual(r.intent_id, intent().id)

    def test_A0_not_an_intent(self):
        for raw in ("재부팅하세요", None, 3, {"action": "throttle"}):
            r = self.v(raw)
            self.assertEqual((r.ok, r.rule), (False, "A0"), raw)
            self.assertRegex(r.intent_id, r"^int-[0-9a-f]{16}$")

    def test_A0_forged_intent_id(self):
        d = intent().to_dict()
        d["intent_id"] = "int-0000000000000000"
        self.assertEqual(self.v(d).rule, "A0")
        self.assertEqual(self.v(intent().to_dict()).rule, "0")     # 받은 dict 도 꼴이 맞으면 통과

    def test_A0_other_dc(self):
        self.assertEqual(self.v(intent(dc_id="dc-other")).rule, "A0")

    def test_A0_not_intents(self):
        d = dc(offers={**dc().offers, "retrieve": ["srv1"], "none": ["srv1"]})
        self.assertEqual(self.v(intent("retrieve", "srv1", {}), d).rule, "A0")
        self.assertEqual(self.v(intent("none", "srv1", {}), d).rule, "A0")

    def test_A1_unoffered(self):
        self.assertEqual(self.v(intent("format_disk", "srv1", {})).rule, "A1")
        d = dc(offers={k: v for k, v in dc().offers.items() if k != "reboot"})    # Model 에 있어도 내놓지 않았으면
        self.assertEqual(self.v(intent("reboot", "srv1", {}), d).rule, "A1")
        d = dc(offers={**dc().offers, "format_disk": ["srv1"]})         # 내놓았어도 ActionSpec 이 없으면
        self.assertEqual(self.v(intent("format_disk", "srv1", {}), d).rule, "A1")

    def test_A2_not_seen(self):
        self.assertEqual(self.v(intent(target="srv99")).rule, "A2")
        r = self.v(intent(target="srv9"))
        self.assertEqual(r.rule, "A2")
        self.assertIn("retrieve h1", r.reasons[0])
        self.assertIn("DROP", self.v(intent(target="srv8")).reasons[0])

    def test_A2_targetless(self):
        self.assertEqual(self.v(intent(target=None)).rule, "A2")          # throttle 은 겨냥이 있어야
        self.assertEqual(self.v(intent("escalate", None, {})).rule, "0")    # 겨냥 없는 행동으로 내놓은 것

    def test_A3_seen_but_not_target(self):
        self.assertEqual(self.v(intent(target="srv2")).rule, "A3")

    def test_A4_args(self):
        for args in ({"level": 9}, {"level": 0}, {}, {"level": 1, "x": 1}, {"level": "2"}, {"level": True},
                     {"level": 2.5}):
            self.assertEqual(self.v(intent(args=args)).rule, "A4", args)
        self.assertEqual(self.v(intent(args={"level": 2.0})).rule, "0")
        self.assertEqual(self.v(intent("open_ticket", "srv1", {"note": 3})).rule, "A4")

    def test_order_first_hit(self):
        # 대상도 틀리고 인자도 틀리면 앞의 규칙(A3)
        self.assertEqual(self.v(intent(target="srv2", args={"level": 9})).rule, "A3")

    def test_exception_fails_closed(self):
        r = validate(intent(), None, model())
        self.assertEqual((r.ok, r.rule), (False, "E"))
