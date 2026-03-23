import pytest

from app.simulation.expression_parser import parse_and_evaluate, ExpressionError


class TestParseAndEvaluate:
    def test_simple_addition(self):
        result = parse_and_evaluate("1 + 2", {})
        assert result == 3.0

    def test_simple_multiplication(self):
        result = parse_and_evaluate("3 * 4", {})
        assert result == 12.0

    def test_subtraction(self):
        result = parse_and_evaluate("10 - 3", {})
        assert result == 7.0

    def test_division(self):
        result = parse_and_evaluate("10 / 4", {})
        assert result == 2.5

    def test_combined_ops(self):
        result = parse_and_evaluate("2 + 3 * 4", {})
        assert result == 14.0

    def test_parentheses(self):
        result = parse_and_evaluate("(2 + 3) * 4", {})
        assert result == 20.0

    def test_negative_number(self):
        result = parse_and_evaluate("-5 + 10", {})
        assert result == 5.0

    def test_variable_substitution(self):
        variables = {"voltage": 230.0, "current": 15.0}
        result = parse_and_evaluate("{voltage} * {current}", variables)
        assert result == 3450.0

    def test_complex_expression_with_vars(self):
        variables = {"v1": 230.0, "v2": 228.0}
        result = parse_and_evaluate("({v1} + {v2}) / 2", variables)
        assert result == 229.0

    def test_missing_variable_returns_zero(self):
        result = parse_and_evaluate("{missing} + 10", {})
        assert result == 10.0

    def test_division_by_zero_returns_zero(self):
        result = parse_and_evaluate("10 / 0", {})
        assert result == 0.0

    def test_reject_function_call(self):
        with pytest.raises(ExpressionError, match="not allowed"):
            parse_and_evaluate("__import__('os')", {})

    def test_reject_attribute_access(self):
        with pytest.raises(ExpressionError, match="not allowed"):
            parse_and_evaluate("x.y", {"x": 1})

    def test_empty_expression(self):
        with pytest.raises(ExpressionError):
            parse_and_evaluate("", {})

    def test_float_literal(self):
        result = parse_and_evaluate("3.14 * 2", {})
        assert abs(result - 6.28) < 0.001
