import unittest

from guard import ALLOW, DENY, SAFE_ACTION, FormError, GuardResult, ValidationResult

IID = "int-0123456789abcdef"


def gr(**kw):
    base = dict(intent_id=IID, verdict=DENY, mode="shadow", rule="A6", state_refs=["srv1.status", "srv1@4"],
                reasons=["[A6] 낡았다"], safe_action=None)
    base.update(kw)
    return GuardResult(**base)


def vr(**kw):
    base = dict(intent_id=IID, ok=False, rule="A2", reasons=["본 적 없다"])
    base.update(kw)
    return ValidationResult(**base)


class RoundTrip(unittest.TestCase):
    def test_round_trip_and_id(self):
        for obj in (gr(), gr(verdict=ALLOW, rule="0", reasons=[]), gr(verdict=SAFE_ACTION, rule="D",
                                                                     safe_action="escalate"), vr(), vr(ok=True, rule="0")):
            d = obj.to_dict()
            self.assertEqual(type(obj).from_dict(d), obj)
            self.assertEqual(type(obj).from_dict(d).to_dict(), d)

    def test_id_prefixes(self):
        self.assertRegex(gr().id, r"^grd-[0-9a-f]{16}$")
        self.assertRegex(vr().id, r"^val-[0-9a-f]{16}$")

    def test_golden_hash(self):
        # 꼴 · 정준 JSON 이 바뀌면 이 값이 바뀐다. 바꾸려면 판본(schema)을 올린다
        self.assertEqual(gr().id, GOLDEN_GUARD)
        self.assertEqual(vr().id, GOLDEN_VALIDATION)

    def test_state_refs_are_a_set(self):
        self.assertEqual(gr(state_refs=["b.x", "a@1"]).id, gr(state_refs=["a@1", "b.x"]).id)
        with self.assertRaises(FormError):
            gr(state_refs=["a@1", "a@1"])

    def test_every_field_changes_the_id(self):
        base = gr()
        for k, v in dict(intent_id="int-fedcba9876543210", rule="A5", mode="enforce", state_refs=["srv2@1"],
                         reasons=["[A6] 다른 까닭"]).items():
            self.assertNotEqual(gr(**{k: v}).id, base.id, k)


class Closed(unittest.TestCase):
    def test_unknown_and_missing_fields(self):
        d = gr().to_dict()
        with self.assertRaises(FormError):
            GuardResult.from_dict({**d, "extra": 1})
        d2 = dict(d)
        del d2["mode"]
        with self.assertRaises(FormError):
            GuardResult.from_dict(d2)
        d3 = dict(vr().to_dict())
        del d3["validation_id"]
        with self.assertRaises(FormError):
            ValidationResult.from_dict(d3)

    def test_forged_id(self):
        d = gr().to_dict()
        d["guard_id"] = "grd-0000000000000000"
        with self.assertRaises(FormError):
            GuardResult.from_dict(d)
        d = gr().to_dict()
        d["verdict"] = ALLOW                      # 판정만 바꿔 넣으면 id 가 맞지 않는다
        d["rule"] = "0"
        with self.assertRaises(FormError):
            GuardResult.from_dict(d)

    def test_other_schema(self):
        with self.assertRaises(FormError):
            gr(schema="guard-result/2")
        with self.assertRaises(FormError):
            vr(schema="validation-result/0")

    def test_values(self):
        bad = [dict(verdict="MAYBE"), dict(mode="loud"), dict(rule="Z9"), dict(intent_id="x"),
               dict(verdict=ALLOW),                              # ALLOW 인데 규칙이 걸림
               dict(verdict=DENY, rule="0"),                     # DENY 인데 규칙 없음
               dict(verdict=SAFE_ACTION, rule="D"),              # 갈아 끼울 행동이 없다
               dict(safe_action="escalate"),                     # DENY 인데 갈아 끼운 행동
               dict(verdict=SAFE_ACTION, rule="D", safe_action=""),
               dict(state_refs=["srv1"]), dict(reasons=[3]), dict(reasons=[""])]
        for kw in bad:
            with self.assertRaises(FormError, msg=kw):
                gr(**kw)
        for kw in [dict(ok=True), dict(ok=False, rule="0"), dict(ok=1, rule="0"), dict(rule="A7")]:
            with self.assertRaises(FormError, msg=kw):
                vr(**kw)


GOLDEN_GUARD = "grd-c92e455946006c7d"
GOLDEN_VALIDATION = "val-9a4a243340a188e3"
