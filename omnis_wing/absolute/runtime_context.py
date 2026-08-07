"""Process-local WING agent binding for adapters without agent args."""
from __future__ import annotations
import contextvars
from typing import Any, Optional

wing_agent_var: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar(
    "omnis_wing_agent", default=None
)

def set_wing_agent(agent: Any):
    return wing_agent_var.set(agent)

def reset_wing_agent(token) -> None:
    wing_agent_var.reset(token)

def get_wing_agent():
    return wing_agent_var.get()
