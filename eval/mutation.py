"""변이 시험 -- Guard 코드를 일부러 망가뜨려 시험이 빨개지는지 본다. 하나라도 초록으로 남으면 그 시험은 헛돈다.

    python3 eval/mutation.py            # 복사본에서 변이마다 시험을 돌린다. 원본은 건드리지 않는다
    python3 eval/mutation.py --ms-only  # MS 대조 시험만으로 몇 개를 잡나(대조가 헛돌지 않나)

변이마다 단위 시험을 먼저 돌리고, 초록이면 MS 대조 시험을 돌린다. 어느 쪽이 잡았는지 찍는다(`unit` · `ms`).
MS 대조에는 MS 저장소가 있어야 한다(옆 디렉터리 또는 MS_REPO). 없으면 돌리지 않는다.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval.dc_fixtures import find_dc  # noqa: E402
from eval.ms_contrast import find_ms  # noqa: E402

R, F, V, C, D = "guard/rules.py", "guard/forms.py", "guard/views.py", "guard/command.py", "guard/dc_adapter.py"
# (이름, 파일, 바꿀 글, 바꿀 것). ★ = "ALLOW 를 더하는" 변이(닫는 쪽으로만을 깨는 것)
MUTANTS = [
    ("★ 걸린 규칙이 있어도 ALLOW", R, "    if not fails:\n", "    if True:\n"),
    ("★ VALIDATE 를 지나치고 GUARD 로", R, "    if not v.ok:\n", "    if False:\n"),
    ("★ Guard 예외를 ALLOW 로", R, 'return GuardResult(iid, DENY, mode, "E", (), [f"[E] Guard 예외',
     'return GuardResult(iid, ALLOW, mode, "0", (), [f"[E] Guard 예외'),
    ("★ Validate 예외를 통과로", R, 'rule, reasons = "E", [f"Validate 예외', 'rule, reasons = PASS, [f"Validate 예외'),
    ("★ D 의 갈아 끼움을 ALLOW 로", R, "return GuardResult(it.id, SAFE_ACTION, mode, rule, refs, reasons, dc.default_action)",
     "return GuardResult(it.id, ALLOW, mode, PASS, refs, [], None)"),
    ("★ enforce 에서만 ALLOW 를 더함", R, "    if not fails:\n", '    if not fails or mode == "enforce":\n'),
    ("★ enforce 에서 VALIDATE 를 지나침", R, "    if not v.ok:\n", '    if not v.ok and mode == "shadow":\n'),
    ("모드에 따라 rule 이 달라짐", R, "rule = next(r for r in GUARD_ORDER if r in fails)",
     'rule = next(r for r in GUARD_ORDER if r in fails) if mode == "shadow" else "E"'),
    ("모드에 따라 까닭이 달라짐", R, 'reasons = [f"[{r}] {w}" for r in GUARD_ORDER if r in fails for w in fails[r]]',
     'reasons = [f"[{r}] {w}" for r in GUARD_ORDER if r in fails for w in fails[r]][: (9 if mode == "shadow" else 1)]'),
    ("모르는 모드를 받음", R, "    if mode not in MODES:\n", "    if False:\n"),
    ("A5 판 비교 생략", R, "elif node.version != dc.seen[it.target]:", "elif False:"),
    ("A5 지금 없음 생략", R, '        if node is None:\n            fails["A5"]', '        if False:\n            fails["A5"]'),
    ("A5 본 판 없음 생략", R, "elif it.target not in dc.seen:", "elif False:"),
    ("A6 생략", R, '    if why:\n        fails["A6"] = why', '    if False:\n        fails["A6"] = why'),
    ("A6 낡음을 봄 생략", R, "if pv is None or pv.stale:", "if pv is None:"),
    ("A6 사전조건 평가 생략", R, "            if not predicate.holds(p, vals):", "            if False:"),
    ("A6 대상 모형 생략", R, 'if spec.target_model not in ("*", node.model):', "if False:"),
    ("A6 겨냥 없는 행동의 사전조건 허용", R, "return [f\"{spec.name} 는 겨냥이 없는데 사전조건이 있다\"] if spec.preconditions else []",
     "return []"),
    ("A7 생략", R, "if spec.risk in GRANT_RISKS and spec.name not in model.grants:", "if False:"),
    ("A7 external 은 허가 없이", R, 'GRANT_RISKS = ("external", "irreversible")', 'GRANT_RISKS = ("irreversible",)'),
    ("A8 생략", R, "if repeat_key(it, version) in state.allowed:", "if False:"),
    ("A8 열쇠에 rationale", R, "[intent.action, intent.target, intent.args]",
     "[intent.action, intent.target, intent.args, intent.rationale]"),
    ("A8 열쇠에 판 없음", R, 'return f"{k}@{version}"', "return k"),
    ("D 생략", R, "if spec.risk in model.risky and", "if False and"),
    ("D 낡은 키를 보지 않음", R, "(not dc.complete or stale):", "(not dc.complete):"),
    ("D 가 안전 기본 후보도 막음", R, "and it.action not in dc.default_decision and", "and"),
    ("★ 실행기 밖 행동으로 갈아 끼움", R, "        if dc.default_action not in model.specs:", "        if False:"),
    ("SAFE_ACTION 을 후보 밖에서", R, " and dc.default_action in dc.default_decision:", ":"),
    ("rule 순서를 MS 와 다르게", R, 'GUARD_ORDER = ("D", "A5", "A6", "A7", "A8")', 'GUARD_ORDER = ("D", "A6", "A5", "A7", "A8")'),
    ("A0 다른 DC 허용", R, "if it.dc_id != dc.dc_id:", "if False:"),
    ("A0 none · retrieve 를 의도로", R, "if it.action in NOT_INTENTS:", "if False:"),
    ("A1 생략", R, "if it.action not in dc.offers:", "if False:"),
    ("A1 ActionSpec 없음 생략", R, '    if spec is None:\n        return "A1"', '    if False:\n        return "A1"'),
    ("A2 생략", R, "        if it.target not in dc.seen:\n            how", "        if False:\n            how"),
    ("A2 겨냥 없음 허용", R, "if None not in targets:", "if False:"),
    ("A3 생략", R, "if it.target not in targets:", "if False:"),
    ("A4 생략", R, '    if bad:\n        return "A4"', '    if False:\n        return "A4"'),
    ("꼴을 연다(모르는 칸)", F, 'errs = [f"모르는 칸 {k!r}" for k in sorted(set(d) - known, key=str)]', "errs = []"),
    ("id 를 다시 계산하지 않음", F, "if d[cls.ID] != obj.id:", "if False:"),
    ("판본을 보지 않음", F, "if self.schema != self.SCHEMA:", "if False:"),
    ("SAFE_ACTION · safe_action 맞춤 생략", F, "if (self.verdict == SAFE_ACTION) != (self.safe_action is not None):", "if False:"),
    ("ALLOW · rule 맞춤 생략", F, "if (self.verdict == ALLOW) != (self.rule == PASS):", "if False:"),
    ("state_refs 를 정렬하지 않음", F, "tuple(sorted(self.state_refs))", "tuple(self.state_refs)"),
    ("해시가 verdict 를 빠뜨림", F, "for f in fields(self)}", 'for f in fields(self) if f.name != "verdict"}'),
    ("DCView 가 후보 밖 기본 행동을 받음", V, "if self.default_action is not None and self.default_action not in self.default_decision:",
     "if False:"),
    ("Prop 의 stale 을 bool 로 보지 않음", V, 'if extra or "stale" not in pv or not isinstance(pv["stale"], bool):', "if extra:"),
    ("기본 위험 등급에서 external 을 뺌", V, 'DEFAULT_RISKY = ("external", "irreversible")', 'DEFAULT_RISKY = ("irreversible",)'),
    ("결과와 의도를 맞대지 않음", C, "if result.intent_id != intent.id:", "if False:"),
    ("SAFE_ACTION 이 겨냥을 물려받음", C, '"target": None, "args": {}}', '"target": intent.target, "args": {}}'),
    ("★ DENY 에도 명령 재료", C, '    raise ValueError(f"{result.verdict} 에는 명령이 없다")',
     '    return {"intent_id": intent.id, "action": intent.action, "target": intent.target, "args": dict(intent.args)}'),
    ("D 범위를 다시 넓힘(문맥 STALE 전부)", R, "return sorted(k for k in dc.stale_keys\n", "return sorted(dc.stale_keys)\nreturn sorted(k for k in dc.stale_keys\n"),
    ("D 가 used_keys 를 무시", R, "    used = set(it.used_keys)\n", "    used = set()\n"),
    ("D 가 필수 키를 무시", R, "req = set(dc.required_keys)", "req = set()"),
    ("D 가 query: 범위를 무시", R, 'queries = {k[len("query:"):] for k in used if k.startswith("query:")}', "queries = set()"),
    ("query: 이름을 앞부분만 맞춤", R, 'k.split("/", 1)[0] in queries', "any(k.startswith(q) for q in queries)"),
    ("어댑터가 required_keys 를 비움", D, "required_keys=tuple(sorted({k for k in states if _role_name(k) in required})))",
     "required_keys=())"),
    ("DC digest 를 맞춰 보지 않음", D, 'if not isinstance(record["digest"], str) or _digest(body) != record["digest"]:', "if False:"),
    ("DC 목적 판본을 보지 않음", D, 'if (purpose["name"], purpose["version"]) != (core["purpose"], core["purpose_version"]):',
     "if False:"),
    ("DC core 칸을 보지 않음", D, "if not isinstance(core, dict) or set(core) != CORE_KEYS:", "if not isinstance(core, dict):"),
    ("NOT_APPLICABLE 을 빠진 것으로", D, " and st != NOT_APPLICABLE]", "]"),
    ("필수 여부를 보지 않음", D, "if _role_name(k) in required and st", "if st"),
    ("필수 기본값을 거짓으로", D, 'if r.get("required", True):', 'if r.get("required", False):'),
    ("꼬리 있는 키의 역할", D, 'return head.split("[", 1)[0], name', "return head, name"),
    ("core 에 없는 필수 키를 넘김", D, '    missing += [f"{r}.{n}" for r, n in sorted(required - present)]\n', ""),
    ("낡은 상태 키를 보지 않음", D, "stale = [k for k, (_, st) in states.items() if st == STALE]", "stale = []"),
    ("낡은 질의 속성을 보지 않음", D, 'stale += [f"{qname}/{row[\'id\']}.{p}" for p, (_, st) in sorted(row["props"].items()) if st == STALE]',
     "pass"),
    ("기본 행동을 목적의 첫 후보로", D, 'default_action=core["default_action"]',
     'default_action=(purpose.get("default_decision") or [None])[0]'),
    ("목적 행동을 내놓지 않음", D, "offered = {a: [None] for a in acts}", "offered = {}"),
    ("DCView 검사 생략", D, "    view.check()\n", ""),
    ("Guard 가 MS 를 import", R, "from action import predicate\n", "from action import predicate\nif False:\n    import ms  # noqa\n"),
    ("★ 자기 술어로 돌아감(사전조건 언제나 참)", R, "from action import predicate\n",
     "from action import predicate as _p\nclass predicate:\n    props_of = staticmethod(_p.props_of)\n    holds = staticmethod(lambda p, v: True)\n"),
    ("자기 인자 검사로 돌아감(검사 안 함)", R, "from action.params import check_args\n",
     "def check_args(params, args):\n    return []\n"),
    ("행동 명세가 ActionModel 의 위험 등급을 버림", V, "specs = {s.name: ActionSpec(**to_guard_spec(s)) for s in model.specs}",
     'specs = {s.name: ActionSpec(**{**to_guard_spec(s), "risk": "local"}) for s in model.specs}'),
    ("ActionModel 길이 허가를 버림", V, "return cls(specs, frozenset(grants), tuple(risky))", "return cls(specs, frozenset(), tuple(risky))"),
]

UNIT = ["tests.test_boundary", "tests.test_command", "tests.test_dc_adapter", "tests.test_forms", "tests.test_guard",
        "tests.test_predicate", "tests.test_validate", "tests.test_views"]


def run(tree: pathlib.Path, mods, env) -> bool:
    r = subprocess.run([sys.executable, "-m", "unittest", "-q", *mods], cwd=tree, capture_output=True, text=True,
                       env=env)
    return r.returncode == 0


def main() -> int:
    ms_only = "--ms-only" in sys.argv
    msroot = find_ms()
    if msroot is None:
        print("MS 를 찾지 못했다(MS_REPO) -- 대조 시험 없이는 변이를 돌리지 않는다")
        return 2
    env = {**os.environ, "MS_REPO": str(msroot)}
    if find_dc() is not None:                    # 있으면 DC 드리프트 시험도 돈다
        env["DC_REPO"] = str(find_dc())
    for k in ("ACTION_REPO",):
        if k not in env:
            for p in (ROOT.parent / "action", ROOT.parent / "cogito5170" / "action"):
                if (p / "action" / "forms.py").exists():
                    env[k] = str(p.resolve())
    survived = []
    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp) / "guard"
        shutil.copytree(ROOT, base, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        if not (run(base, UNIT, env) and run(base, ["tests.test_contrast_ms"], env)):
            print("원본이 초록이 아니다 -- 변이를 돌리지 않는다")
            return 2
        for name, rel, old, new in MUTANTS:
            path = base / rel
            orig = path.read_text(encoding="utf-8")
            if orig.count(old) != 1:
                print(f"??        {name}: 바꿀 글이 {orig.count(old)} 번 나온다")
                survived.append(name)
                continue
            path.write_text(orig.replace(old, new), encoding="utf-8")
            try:
                if ms_only:
                    caught = "ms" if not run(base, ["tests.test_contrast_ms"], env) else None
                else:
                    caught = "unit" if not run(base, UNIT, env) else (
                        "ms" if not run(base, ["tests.test_contrast_ms"], env) else None)
            finally:
                path.write_text(orig, encoding="utf-8")
            print(f"{'SURVIVED' if caught is None else 'RED ' + caught:<9} {name}")
            if caught is None:
                survived.append(name)
    print(f"\n{len(MUTANTS) - len(survived)}/{len(MUTANTS)} RED")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
