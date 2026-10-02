import unittest

from action.forms import ActionCommand

from guard import build_command, command_material, guard
from tests.fixture import dc, intent, model, state


class Material(unittest.TestCase):
    def test_allow_carries_the_intent(self):
        it = intent()
        r = guard(it, dc(), state(), model())
        mat = command_material(r, it)
        self.assertEqual(mat, {"intent_id": it.id, "action": "throttle", "target": "srv1", "args": {"level": 2}})
        cmd = build_command(mat, decision_ref="dr-1", issued_at=1000.0, deadline=2000.0)
        self.assertEqual(ActionCommand.from_dict(cmd.to_dict()), cmd)
        self.assertEqual((cmd.intent_id, cmd.decision_ref, cmd.action), (it.id, "dr-1", "throttle"))

    def test_safe_action_replaces_action_target_args(self):
        it = intent("reboot", "srv1", {})
        r = guard(it, dc(complete=False), state(), model())
        mat = command_material(r, it)
        self.assertEqual(mat, {"intent_id": it.id, "action": "escalate", "target": None, "args": {}})
        build_command(mat, "dr-2", 1.0)

    def test_deny_has_no_command(self):
        it = intent(target="srv3")
        with self.assertRaises(ValueError):
            command_material(guard(it, dc(), state(), model()), it)

    def test_result_must_belong_to_intent(self):
        r = guard(intent(), dc(), state(), model())
        with self.assertRaises(ValueError):
            command_material(r, intent(rationale="다른 의도"))
