import unittest

from action.forms import ContractError
from action.spec import ActionModel
from action.spec import ActionSpec as SpecA
from action.spec import to_guard_spec

from guard import ActionSpec, DCView, GuardModel, StateView, ViewError, guard
from tests.fixture import dc, intent, model


DC = {"dc_id": "dc-test-1", "offers": {"throttle": ["srv1"]}, "seen": {"srv1": 4}, "complete": True,
      "stale_keys": [], "default_decision": ["escalate"], "default_action": "escalate"}
ST = {"entities": {"srv1": {"model": "Server", "version": 4, "props": {"status": {"value": "hot", "stale": False}}}},
      "allowed": []}


class Views(unittest.TestCase):
    def test_from_dict(self):
        d = DCView.from_dict(DC)
        self.assertEqual(d.default_decision, ("escalate",))
        s = StateView.from_dict(ST)
        self.assertEqual(s.entities["srv1"].props["status"].value, "hot")
        m = GuardModel.from_dict({"specs": [{"name": "throttle", "target_model": "Server", "risk": "local",
                                             "preconditions": [["status", "in", ["hot"]]],
                                             "params": {"level": {"type": "integer"}}}], "grants": []})
        self.assertEqual(guard(intent(args={"level": 1}), d, s, m).verdict, "ALLOW")

    def test_closed(self):
        for bad in ({**DC, "extra": 1}, {**DC, "default_action": "reboot"}, {**DC, "seen": {"srv1": True}},
                    {**DC, "complete": "yes"}, {**DC, "dc_id": ""}, {**DC, "offers": {"throttle": "srv1"}}):
            with self.assertRaises(ViewError, msg=bad):
                DCView.from_dict(bad)
        e = ST["entities"]["srv1"]
        for bad in ({**ST, "extra": 1},
                    {"entities": {"srv1": {**e, "x": 1}}},
                    {"entities": {"srv1": {**e, "version": "4"}}},
                    {"entities": {"srv1": {**e, "props": {"status": {"value": "hot"}}}}},
                    {"entities": {"srv1": {**e, "props": {"status": {"value": "hot", "stale": 0}}}}},
                    {"entities": {"srv1": {**e, "props": {"status": {"value": "hot", "stale": False, "q": 1}}}}}):
            with self.assertRaises(ViewError, msg=bad):
                StateView.from_dict(bad)
        for bad in ({"name": "x", "risk": "scary"}, {"name": "x", "preconditions": [["s", "~", 1]]},
                    {"name": "x", "owner": "me"}):
            with self.assertRaises(ViewError, msg=bad):
                ActionSpec.from_dict(bad)
        with self.assertRaises(ViewError):
            GuardModel.from_dict({"specs": [], "risky": ["huge"]})
        with self.assertRaises(ViewError):
            GuardModel.from_dict({"specs": [], "owner": "me"})

    def test_default_risky(self):
        self.assertEqual(model().risky, ("external", "irreversible"))
        self.assertEqual(GuardModel.from_dict({"specs": []}).risky, ("external", "irreversible"))
        self.assertEqual(dc().complete, True)


class FromActionModel(unittest.TestCase):
    """CMD-G5 · BD-109: 행동 명세는 ActionModel 에서, 허가 · 위험 등급은 운영자 설정으로."""

    def am(self):
        return ActionModel("am-test-1", (
            SpecA("throttle", "1", "Server", {"level": {"type": "integer", "min": 1, "max": 3}},
                  (("status", "in", ["hot", "critical"]),), "local",
                  ({"entity": "$target", "pred": ["throttled", "==", True]},), 60000.0, "느리게"),
            SpecA("reboot", "2", "Server", {}, (("status", "==", "critical"),), "irreversible"),
            SpecA("ESCALATE", "1", None, {}, (), "external")))

    def test_specs_are_the_guard_projection(self):
        m = GuardModel.from_action_model(self.am(), grants=("reboot",), risky=("irreversible",))
        self.assertEqual(sorted(m.specs), ["ESCALATE", "reboot", "throttle"])
        for s in self.am().specs:
            self.assertEqual(m.specs[s.name], ActionSpec(**to_guard_spec(s)))
        t = m.specs["throttle"]                          # 사후조건 · 창 · 판본 · 설명은 Guard 에 오지 않는다
        self.assertEqual((t.target_model, t.risk, t.preconditions), ("Server", "local", (("status", "in", ["hot", "critical"]),)))
        self.assertEqual((m.grants, m.risky), (frozenset({"reboot"}), ("irreversible",)))   # 운영자 설정은 그대로
        self.assertEqual(GuardModel.from_action_model(self.am()).grants, frozenset())       # 기본은 허가 없음
        self.assertEqual(GuardModel.from_action_model(self.am()).risky, ("external", "irreversible"))

    def test_same_verdicts_as_hand_built(self):
        a = GuardModel.from_action_model(self.am(), grants=("reboot",))
        h = GuardModel({"throttle": ActionSpec("throttle", "Server", {"level": {"type": "integer", "min": 1, "max": 3}},
                                               (("status", "in", ["hot", "critical"]),), "local"),
                        "reboot": ActionSpec("reboot", "Server", {}, (("status", "==", "critical"),), "irreversible"),
                        "ESCALATE": ActionSpec("ESCALATE", None, {}, (), "external")}, frozenset({"reboot"}))
        self.assertEqual(a, h)

    def test_refuses(self):
        with self.assertRaises(ViewError):
            GuardModel.from_action_model({"specs": []})
        with self.assertRaises(ViewError):
            GuardModel.from_action_model(self.am(), risky=("huge",))
        with self.assertRaises(ContractError):            # 명세의 모양은 action 이 거른다
            ActionModel("am-x", (SpecA("bad", "1", risk="scary"),))
