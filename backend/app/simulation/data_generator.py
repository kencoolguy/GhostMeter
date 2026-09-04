"""Stateless data generator — produces register values based on mode and params."""

import logging
import math
import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from app.simulation.aggregate import DEFAULT_ON_MISSING
from app.simulation.expression_parser import parse_and_evaluate

logger = logging.getLogger(__name__)


@dataclass
class GeneratorContext:
    """Context passed to the generator for each tick."""

    current_values: dict[str, float]
    elapsed_seconds: float
    tick_count: int
    current_hour_utc: float | None = None  # Override for testing; None = use real time
    # Cross-device views for the ``aggregate`` mode (issue #95). ``peer_values``
    # holds the live values of currently running devices; ``peer_last_known``
    # holds the last values a device produced before it stopped / restarted.
    peer_values: Mapping[UUID, Mapping[str, float]] = field(default_factory=dict)
    peer_last_known: Mapping[UUID, Mapping[str, float]] = field(default_factory=dict)


class DataGenerator:
    """Generates register values based on configured data mode."""

    def generate(self, mode: str, params: dict, context: GeneratorContext) -> float:
        match mode:
            case "static":
                return self._generate_static(params)
            case "random":
                return self._generate_random(params)
            case "daily_curve":
                return self._generate_daily_curve(params, context)
            case "computed":
                return self._generate_computed(params, context)
            case "accumulator":
                return self._generate_accumulator(params, context)
            case "aggregate":
                return self._generate_aggregate(params, context)
            case _:
                raise ValueError(f"Unknown data mode: {mode}")

    def _generate_static(self, params: dict) -> float:
        return float(params["value"])

    def _generate_random(self, params: dict) -> float:
        base = float(params["base"])
        amplitude = float(params["amplitude"])
        distribution = params.get("distribution", "uniform")
        if distribution == "gaussian":
            sigma = amplitude / 3
            return base + random.gauss(0, sigma)
        else:
            return base + random.uniform(-amplitude, amplitude)

    def _generate_daily_curve(self, params: dict, context: GeneratorContext) -> float:
        base = float(params["base"])
        amplitude = float(params["amplitude"])
        peak_hour = float(params.get("peak_hour", 14))
        if context.current_hour_utc is not None:
            now_hour = context.current_hour_utc
        else:
            now = datetime.now(timezone.utc)
            now_hour = now.hour + now.minute / 60.0
        offset = amplitude * math.sin(math.pi * (now_hour - peak_hour + 6) / 12)
        return base + offset

    def _generate_computed(self, params: dict, context: GeneratorContext) -> float:
        expression = params["expression"]
        return parse_and_evaluate(expression, context.current_values)

    def _generate_accumulator(self, params: dict, context: GeneratorContext) -> float:
        start_value = float(params.get("start_value", 0.0))
        increment = float(params["increment_per_second"])
        return start_value + increment * context.elapsed_seconds

    def _generate_aggregate(self, params: dict, context: GeneratorContext) -> float:
        """Aggregate a register across other devices.

        Expects engine-normalized params: ``sources`` is a list of device UUIDs
        (already resolved from names) and ``register`` is filled in (defaults to
        the aggregating register's own name).

        Missing values (source not running / register not yet produced) follow
        ``on_missing``: ``last_known`` falls back to the value the source last
        produced (skipped if it never did), ``zero`` contributes 0.0, ``skip``
        drops the source. With no contributing sources the result is 0.0.
        """
        op = params.get("op", "sum")
        register = params["register"]
        weight_register = params.get("weight_register")
        on_missing = params.get("on_missing", DEFAULT_ON_MISSING)

        values: list[float] = []
        weights: list[float] = []
        for source in params["sources"]:
            live = context.peer_values.get(source)
            value = live.get(register) if live is not None else None
            weight = None
            if value is not None and weight_register:
                weight = live.get(weight_register)  # type: ignore[union-attr]

            if value is None:
                if on_missing == "zero":
                    value, weight = 0.0, 0.0
                elif on_missing == "last_known":
                    stale = context.peer_last_known.get(source)
                    value = stale.get(register) if stale is not None else None
                    if value is None:
                        continue
                    if weight_register:
                        weight = stale.get(weight_register)  # type: ignore[union-attr]
                else:  # skip
                    continue

            values.append(float(value))
            weights.append(float(weight) if weight is not None else 0.0)

        if not values:
            return 0.0

        match op:
            case "sum":
                return sum(values)
            case "avg":
                return sum(values) / len(values)
            case "max":
                return max(values)
            case "min":
                return min(values)
            case "weighted_avg":
                total_weight = sum(weights)
                if total_weight == 0:
                    # No usable weights (e.g. all sources idle) — degrade to a plain mean
                    return sum(values) / len(values)
                return sum(v * w for v, w in zip(values, weights)) / total_weight
            case _:
                raise ValueError(f"Unknown aggregate op: {op}")
