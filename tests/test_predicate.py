import unittest

from guard import predicate as P


class Predicate(unittest.TestCase):
    def test_ops(self):
        v = {"t": 80, "s": "hot", "f": None}
        self.assertTrue(P.holds(["t", ">", 70], v))
        self.assertFalse(P.holds(["t", "<", 70], v))
        self.assertTrue(P.holds(["s", "in", ["hot", "critical"]], v))
        self.assertTrue(P.holds(["s", "not_in", ["normal"]], v))
        self.assertTrue(P.holds(["t", "==", 80], v))
        self.assertTrue(P.holds(["t", "!=", 81], v))

    def test_unknown_is_false(self):
        v = {"t": 80, "s": "hot"}
        self.assertFalse(P.holds(["x", "==", None], v))           # 없는 속성은 거짓
        self.assertFalse(P.holds(["x", "!=", 1], v))
        self.assertFalse(P.holds(["s", "<", 3], v))               # 비교할 수 없으면 거짓
        self.assertTrue(P.holds(["x", "missing"], v))
        self.assertFalse(P.holds(["x", "exists"], v))
        self.assertTrue(P.holds(["t", "exists"], v))

    def test_prop_reference(self):
        pred = ["used", ">=", {"prop": "budget", "mul": 0.9}]
        self.assertTrue(P.holds(pred, {"used": 95, "budget": 100}))
        self.assertFalse(P.holds(pred, {"used": 85, "budget": 100}))
        self.assertFalse(P.holds(pred, {"used": 95}))                    # 걸린 속성이 없으면 거짓
        self.assertFalse(P.holds(pred, {"used": 95, "budget": True}))    # 수가 아니면 거짓
        self.assertEqual(P.props_of([pred, ["s", "==", "x"]]), ["used", "budget", "s"])

    def test_check(self):
        self.assertEqual(P.check(["t", ">", 1]), [])
        for bad in (["t"], ["t", "~", 1], ["t", "in", 3], ["t", "eq"], ["t", "in", {"prop": "x"}],
                    ["t", ">", {"prop": 3}], ["t", ">", {"prop": "x", "add": 1}]):
            self.assertTrue(P.check(bad), bad)
