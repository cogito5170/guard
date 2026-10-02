"""경계 -- Guard 는 Policy · CR · MS · DC 를 import 하지 않는다(BD-07 · BD-28). 의존은 action 계약(커밋 고정)과 표준 라이브러리."""
import ast
import pathlib
import sys
import unittest

import action.forms

PKG = pathlib.Path(__file__).resolve().parent.parent / "guard"
ROOT = PKG.parent
ALLOWED_TOP = {"action", "guard", "__future__"} | set(sys.stdlib_module_names)


class Imports(unittest.TestCase):
    def test_only_action_and_stdlib(self):
        bad = []
        for f in sorted(PKG.glob("*.py")):
            for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [node.module]
                else:
                    continue
                bad += [f"{f.name}: {n}" for n in names if n.split(".")[0] not in ALLOWED_TOP]
        self.assertEqual(bad, [])

    def test_action_contract_is_pinned(self):
        self.assertEqual(action.forms.SPEC, "action-contract/1")
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("git+https://github.com/cogito5170/action@3995fdb3ba487f31d841d3e11b710e64f0d523db", text)


class OneLanguage(unittest.TestCase):
    """CMD-G5 · BD-108: 술어 · 인자 검사의 자기 구현이 guard 안에 남지 않는다. action 의 한 벌을 쓴다."""

    def test_shims_only_reexport(self):
        """guard/predicate.py · params.py 는 action 의 대조 시험 때문에 남긴 흔적이다. import 말고는 아무것도 없어야 한다."""
        import action.params
        import action.predicate
        from guard import params, predicate
        for name, mod in (("predicate.py", "action.predicate"), ("params.py", "action.params")):
            body = ast.parse((PKG / name).read_text(encoding="utf-8")).body
            kinds = [type(n).__name__ for n in body
                     if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]   # 머리말 글은 빼고
            self.assertEqual(kinds, ["ImportFrom"], name)
            self.assertEqual(body[-1].module, mod, name)
        self.assertIs(predicate.holds, action.predicate.holds)
        self.assertIs(params.check_args, action.params.check_args)

    def test_no_own_predicate_or_params(self):
        own = []
        for f in sorted(PKG.glob("*.py")):
            for node in ast.parse(f.read_text(encoding="utf-8")).body:        # 모듈 최상위(메서드 DCView.check 는 아니다)
                if isinstance(node, ast.FunctionDef) and node.name in ("holds", "check", "props_of", "check_args",
                                                                       "coerce", "_rhs", "all_hold"):
                    own.append(f"{f.name}: {node.name}")
                if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "OPS" for t in node.targets):
                    own.append(f"{f.name}: OPS")
        self.assertEqual(own, [])

    def test_rules_use_the_action_language(self):
        import action.params
        import action.predicate
        from guard import rules, views
        self.assertIs(rules.predicate, action.predicate)
        self.assertIs(rules.check_args, action.params.check_args)
        self.assertIs(views.predicate, action.predicate)
