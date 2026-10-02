"""작은 세계 하나 -- 서버 셋 · 행동 다섯. 시험마다 고쳐 쓴다."""
from action.forms import ActionIntent

from guard import ActionSpec, DCView, Entity, GuardModel, Prop, StateView

DC_ID = "dc-test-1"

SPECS = [
    ActionSpec("throttle", "Server", {"level": {"type": "integer", "min": 1, "max": 3}},
               (("status", "in", ["hot", "critical"]),), "local"),
    ActionSpec("reboot", "Server", {}, (("status", "==", "critical"),), "irreversible"),
    ActionSpec("open_ticket", "Server", {"note": {"type": "string"}}, (("fan", "==", "failed"),), "external"),
    ActionSpec("escalate", None, {}, (), "external"),
    ActionSpec("inspect", "*", {}, (), "read"),
]


def model(grants=("reboot", "open_ticket", "escalate"), risky=None):
    kw = {} if risky is None else {"risky": tuple(risky)}
    return GuardModel({s.name: s for s in SPECS}, frozenset(grants), **kw)


def dc(**kw):
    base = dict(
        dc_id=DC_ID,
        offers={"throttle": ["srv1", "srv3"], "reboot": ["srv1"], "open_ticket": ["srv1"], "escalate": [None],
                "inspect": ["srv1", "srv2", "srv3"]},
        seen={"srv1": 4, "srv2": 2, "srv3": 7},
        decisions={"srv1": "KEEP", "srv2": "KEEP", "srv3": "KEEP", "srv9": "SUMMARIZE", "srv8": "DROP"},
        handles={"h1": ["srv9"]},
        complete=True, stale_keys=(), default_decision=("escalate", "stop"), default_action="escalate")
    base.update(kw)
    return DCView(**base)


def state(allowed=(), **over):
    ents = {
        "srv1": Entity("Server", 4, {"status": Prop("critical", False, 3.0), "fan": Prop("failed", False, 3.0)}),
        "srv2": Entity("Server", 2, {"status": Prop("normal", False, 3.0)}),
        "srv3": Entity("Server", 7, {"status": Prop("hot", True, 200.0)}),
        "rack": Entity("Rack", 1, {}),
    }
    ents.update(over)
    return StateView(ents, frozenset(allowed))


def intent(action="throttle", target="srv1", args=None, **kw):
    base = dict(dc_id=DC_ID, policy="ms-cr@cr-3", action=action, target=target,
                args={"level": 2} if args is None and action == "throttle" else (args or {}),
                rationale="시험", used_keys=("status",), author_kind="llm")
    base.update(kw)
    return ActionIntent(**base)
