"""The Python escape hatch for scenario values that cannot be literals.

A scenario JSON may write ``{"plugin": "<name>", ...kwargs}`` anywhere the
loader allows it; at run time the registered function is called with a
``ScenarioContext`` and the remaining keys as kwargs.

S1 registers nothing — the synthetic price/solar arrays and literal entity
states cover everything S1 needs. The three EV helpers
(``remainder_soc``, ``ready_u_zero``, ``day_rollover``) are registered here
in S2.
"""

from __future__ import annotations

from typing import Callable

_REGISTRY: dict[str, Callable] = {}


def plugin(name: str) -> Callable[[Callable], Callable]:
    def register(fn: Callable) -> Callable:
        if name in _REGISTRY:
            raise ValueError(f"plugin {name!r} already registered")
        _REGISTRY[name] = fn
        return fn

    return register


def get_plugin(name: str) -> Callable:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"unknown scenario plugin {name!r}; registered: {sorted(_REGISTRY)}"
        ) from None


def registered() -> list[str]:
    return sorted(_REGISTRY)
