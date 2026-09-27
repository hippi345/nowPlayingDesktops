"""Wallpaper apply stage timings for profiling."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ApplyTiming:
    enabled: bool = True
    fetch_seconds: float = 0.0
    compose_seconds: float = 0.0
    save_seconds: float = 0.0
    set_seconds: float = 0.0
    cache_status: str = "miss"
    _stages: dict[str, float] = field(default_factory=dict)

    @classmethod
    def disabled(cls) -> ApplyTiming:
        return cls(enabled=False)

    def note_cache(self, status: str) -> None:
        self.cache_status = status

    @contextmanager
    def stage(self, name: str):
        if not self.enabled:
            yield
            return
        started = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - started
            self._stages[name] = self._stages.get(name, 0.0) + elapsed
            if name == "fetch":
                self.fetch_seconds += elapsed
            elif name == "compose":
                self.compose_seconds += elapsed
            elif name == "save":
                self.save_seconds += elapsed
            elif name == "set":
                self.set_seconds += elapsed
            logger.debug("Apply stage %s took %.3fs", name, elapsed)

    def log_summary(self, *, prefix: str | None = None) -> None:
        if not self.enabled:
            return
        total = sum(self._stages.values())
        for name, elapsed in sorted(self._stages.items()):
            if name not in {"fetch", "compose", "save", "set"}:
                logger.debug("Apply stage %s took %.3fs (detail)", name, elapsed)
        lead = f"{prefix} " if prefix else ""
        logger.info(
            "%sApply took %.2fs (fetch=%.2fs, compose=%.2fs, save=%.2fs, set=%.2fs, cache=%s)",
            lead,
            total,
            self.fetch_seconds,
            self.compose_seconds,
            self.save_seconds,
            self.set_seconds,
            self.cache_status,
        )
