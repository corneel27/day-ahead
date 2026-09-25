"""Registry-indexed read access to a solved mip model.

day_ahead.py never names its variables. The _debug_capture_vars hook builds
a registry (da_debug.build_var_registry) mapping var.idx to
(container_name, index_tuple). Every Tier A invariant reads the model
through this view rather than parsing Dutch log lines, so a model that grows
a new variable family is visible here instead of silently missing.
"""

from __future__ import annotations

from typing import Iterator


class ModelView:
    def __init__(self, model, registry):
        self.model = model
        self.registry = registry
        self.by_container: dict[str, dict[tuple, int]] = {}
        for vidx, (name, idx) in registry.by_idx.items():
            self.by_container.setdefault(name, {})[idx] = vidx

    def has(self, name: str) -> bool:
        return name in self.by_container

    def containers(self) -> list[str]:
        return sorted(self.by_container)

    def value(self, name: str, *index):
        return self.model.vars[self.by_container[name][tuple(index)]].x

    def var(self, name: str, *index):
        return self.model.vars[self.by_container[name][tuple(index)]]

    def items(self, name: str) -> Iterator[tuple[tuple, float]]:
        for idx, vidx in self.by_container.get(name, {}).items():
            yield idx, self.model.vars[vidx].x

    @property
    def max_u(self) -> int:
        from dao.prog.da_debug import _max_known_interval

        return _max_known_interval(self.registry.by_idx)
