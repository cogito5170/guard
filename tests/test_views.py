import unittest

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
