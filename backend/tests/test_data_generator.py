import pytest

from app.simulation.data_generator import DataGenerator, GeneratorContext


@pytest.fixture
def generator():
    return DataGenerator()


@pytest.fixture
def base_context():
    return GeneratorContext(
        current_values={},
        elapsed_seconds=0.0,
        tick_count=0,
    )


class TestStaticMode:
    def test_returns_fixed_value(self, generator, base_context):
        result = generator.generate("static", {"value": 230.0}, base_context)
        assert result == 230.0

    def test_returns_zero(self, generator, base_context):
        result = generator.generate("static", {"value": 0.0}, base_context)
        assert result == 0.0


class TestRandomMode:
    def test_uniform_within_range(self, generator, base_context):
        params = {"base": 230.0, "amplitude": 5.0, "distribution": "uniform"}
        for _ in range(100):
            result = generator.generate("random", params, base_context)
            assert 225.0 <= result <= 235.0

    def test_gaussian_mostly_within_range(self, generator, base_context):
        params = {"base": 230.0, "amplitude": 5.0, "distribution": "gaussian"}
        results = [generator.generate("random", params, base_context) for _ in range(1000)]
        within_range = sum(1 for r in results if 225.0 <= r <= 235.0)
        assert within_range / 1000 > 0.95

    def test_default_distribution_is_uniform(self, generator, base_context):
        params = {"base": 100.0, "amplitude": 10.0}
        for _ in range(100):
            result = generator.generate("random", params, base_context)
            assert 90.0 <= result <= 110.0


class TestDailyCurveMode:
    def test_peak_at_peak_hour(self, generator):
        params = {"base": 230.0, "amplitude": 10.0, "peak_hour": 14}
        context = GeneratorContext(
            current_values={},
            elapsed_seconds=0.0,
            tick_count=0,
            current_hour_utc=14.0,
        )
        result = generator.generate("daily_curve", params, context)
        assert abs(result - 240.0) < 0.1

    def test_trough_12h_after_peak(self, generator):
        params = {"base": 230.0, "amplitude": 10.0, "peak_hour": 14}
        context = GeneratorContext(
            current_values={},
            elapsed_seconds=0.0,
            tick_count=0,
            current_hour_utc=2.0,
        )
        result = generator.generate("daily_curve", params, context)
        assert abs(result - 220.0) < 0.1


class TestComputedMode:
    def test_simple_multiplication(self, generator):
        context = GeneratorContext(
            current_values={"voltage": 230.0, "current": 15.0},
            elapsed_seconds=0.0,
            tick_count=0,
        )
        params = {"expression": "{voltage} * {current}"}
        result = generator.generate("computed", params, context)
        assert result == 3450.0

    def test_missing_variable_uses_zero(self, generator):
        context = GeneratorContext(
            current_values={},
            elapsed_seconds=0.0,
            tick_count=0,
        )
        params = {"expression": "{missing} + 100"}
        result = generator.generate("computed", params, context)
        assert result == 100.0


class TestAccumulatorMode:
    def test_accumulates_over_time(self, generator):
        params = {"start_value": 1000.0, "increment_per_second": 0.5}
        context = GeneratorContext(
            current_values={},
            elapsed_seconds=120.0,
            tick_count=120,
        )
        result = generator.generate("accumulator", params, context)
        assert result == 1060.0

    def test_zero_elapsed(self, generator):
        params = {"start_value": 500.0, "increment_per_second": 1.0}
        context = GeneratorContext(
            current_values={},
            elapsed_seconds=0.0,
            tick_count=0,
        )
        result = generator.generate("accumulator", params, context)
        assert result == 500.0


class TestInvalidMode:
    def test_unknown_mode_raises(self, generator, base_context):
        with pytest.raises(ValueError, match="Unknown data mode"):
            generator.generate("unknown_mode", {}, base_context)
