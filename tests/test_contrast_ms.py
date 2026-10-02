"""MS `arbiter.py` 와의 대조(CMD-G1 끝난 기준 1). MS 가 옆 디렉터리(또는 MS_REPO)에 없으면 건너뛴다."""
import unittest

from eval import ms_contrast


@unittest.skipIf(ms_contrast.find_ms() is None, "MS 저장소가 옆에 없다(MS_REPO)")
class AgainstMS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rep = ms_contrast.run()

    def test_same_verdicts(self):
        self.assertEqual(self.rep["diffs"][:5], [])
        self.assertEqual(self.rep["matched"], self.rep["compared"])

    def test_action_model_path_equals_registry_path(self):
        self.assertEqual(self.rep.get("model_mismatch", 0), 0)

    def test_every_rule_is_exercised(self):
        for rule in ("0", "A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "E"):
            self.assertGreater(self.rep["by_rule"].get(rule, 0), 0, rule)
