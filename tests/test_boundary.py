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
        self.assertIn("git+https://github.com/cogito5170/action@443f8eb810ce3cb9677cdc9f564ff79790f9c2ec", text)
