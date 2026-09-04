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


class TestAggregateMode:
    """``aggregate`` reads other devices' values via the context peer views.

    Params are engine-normalized here: ``sources`` already resolved to UUIDs
    and ``register`` filled in.
    """

    @staticmethod
    def _ctx(peer_values, peer_last_known=None):
        return GeneratorContext(
            current_values={},
            elapsed_seconds=0.0,
            tick_count=0,
            peer_values=peer_values,
            peer_last_known=peer_last_known or {},
        )

    def setup_method(self):
        import uuid

        self.a, self.b, self.c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        self.live = {
            self.a: {"energy": 10.0, "power": 100.0},
            self.b: {"energy": 20.0, "power": 300.0},
            self.c: {"energy": 30.0, "power": 0.0},
        }

    def _params(self, op="sum", sources=None, **extra):
        return {
            "op": op,
            "sources": sources if sources is not None else [self.a, self.b, self.c],
            "register": "energy",
            **extra,
        }

    def test_sum(self, generator):
        assert generator.generate("aggregate", self._params("sum"), self._ctx(self.live)) == 60.0

    def test_avg(self, generator):
        assert generator.generate("aggregate", self._params("avg"), self._ctx(self.live)) == 20.0

    def test_max_min(self, generator):
        ctx = self._ctx(self.live)
        assert generator.generate("aggregate", self._params("max"), ctx) == 30.0
        assert generator.generate("aggregate", self._params("min"), ctx) == 10.0

    def test_weighted_avg(self, generator):
        params = self._params("weighted_avg", weight_register="power")
        # (10*100 + 20*300 + 30*0) / (100 + 300 + 0) = 7000 / 400
        result = generator.generate("aggregate", params, self._ctx(self.live))
        assert result == pytest.approx(17.5)

    def test_weighted_avg_zero_weights_falls_back_to_mean(self, generator):
        live = {k: {**v, "power": 0.0} for k, v in self.live.items()}
        params = self._params("weighted_avg", weight_register="power")
        assert generator.generate("aggregate", params, self._ctx(live)) == 20.0

    def test_missing_source_last_known_uses_stale_value(self, generator):
        live = {self.a: self.live[self.a], self.b: self.live[self.b]}  # c stopped
        stale = {self.c: {"energy": 29.5}}
        params = self._params("sum", on_missing="last_known")
        assert generator.generate("aggregate", params, self._ctx(live, stale)) == 59.5

    def test_missing_source_last_known_never_seen_is_skipped(self, generator):
        live = {self.a: self.live[self.a], self.b: self.live[self.b]}
        params = self._params("avg", on_missing="last_known")
        assert generator.generate("aggregate", params, self._ctx(live)) == 15.0

    def test_missing_source_zero_counts_toward_avg(self, generator):
        live = {self.a: self.live[self.a], self.b: self.live[self.b]}
        params = self._params("avg", on_missing="zero")
        assert generator.generate("aggregate", params, self._ctx(live, {self.c: {"energy": 99}})) \
            == 10.0

    def test_missing_source_skip_ignores_stale(self, generator):
        live = {self.a: self.live[self.a], self.b: self.live[self.b]}
        params = self._params("sum", on_missing="skip")
        assert generator.generate("aggregate", params, self._ctx(live, {self.c: {"energy": 99}})) \
            == 30.0

    def test_running_source_without_register_yet_is_missing(self, generator):
        live = {self.a: {}, self.b: self.live[self.b]}  # a started, no tick yet
        params = self._params("sum", sources=[self.a, self.b], on_missing="last_known")
        assert generator.generate("aggregate", params, self._ctx(live, {self.a: {"energy": 1}})) \
            == 21.0

    def test_no_contributing_sources_returns_zero(self, generator):
        params = self._params("sum", on_missing="skip")
        assert generator.generate("aggregate", params, self._ctx({})) == 0.0

    def test_unknown_op_raises(self, generator):
        with pytest.raises(ValueError, match="Unknown aggregate op"):
            generator.generate("aggregate", self._params("median"), self._ctx(self.live))
