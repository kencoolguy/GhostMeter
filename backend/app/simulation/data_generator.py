"""Stateless data generator — produces register values based on mode and params."""

import logging
import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone

from app.simulation.expression_parser import parse_and_evaluate

logger = logging.getLogger(__name__)


@dataclass
class GeneratorContext:
    """Context passed to the generator for each tick."""

    current_values: dict[str, float]
    elapsed_seconds: float
    tick_count: int
    current_hour_utc: float | None = None  # Override for testing; None = use real time


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
