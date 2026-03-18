"""Safe AST-based arithmetic expression parser.

Supports: +, -, *, / with float/int literals and {variable} references.
Rejects: function calls, attribute access, imports, all other node types.

Security: Uses ast.parse() with manual AST traversal. Does NOT use the
built-in Python code execution functions. Only numeric constants and
the four basic arithmetic operators are permitted.
"""

import ast
import logging
import re

logger = logging.getLogger(__name__)

_VAR_PATTERN = re.compile(r"\{(\w+)\}")


class ExpressionError(Exception):
    """Raised when an expression cannot be parsed or contains disallowed constructs."""


def parse_and_evaluate(expression: str, variables: dict[str, float]) -> float:
    """Parse and evaluate a simple arithmetic expression safely.

    Args:
        expression: An arithmetic expression string. Variables are referenced
            with curly braces, e.g. ``"{voltage} * {current}"``.
        variables: A mapping of variable names to their float values.

    Returns:
        The evaluated result as a float.

    Raises:
        ExpressionError: If the expression is empty, contains a syntax error,
            or uses disallowed constructs (function calls, attribute access, etc.).
    """
    if not expression or not expression.strip():
        raise ExpressionError("Empty expression")

    def _replace_var(match: re.Match) -> str:
        name = match.group(1)
        value = variables.get(name)
        if value is None:
            logger.warning("Expression variable '%s' not found, using 0.0", name)
            return "0.0"
        return str(value)

    substituted = _VAR_PATTERN.sub(_replace_var, expression)

    try:
        tree = ast.parse(substituted, mode="eval")
    except SyntaxError as e:
        raise ExpressionError(f"Syntax error in expression: {e}") from e

    return _safe_ast_eval(tree.body)


def _safe_ast_eval(node: ast.AST) -> float:
    """Recursively walk an AST node, allowing only safe arithmetic operations.

    Args:
        node: An AST node from an expression tree.

    Returns:
        The evaluated float result.

    Raises:
        ExpressionError: If the node type or operator is not allowed.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _safe_ast_eval(node.operand)
        if isinstance(node.op, ast.USub):
            return -operand
        return operand

    if isinstance(node, ast.BinOp):
        left = _safe_ast_eval(node.left)
        right = _safe_ast_eval(node.right)

        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                logger.warning("Division by zero in expression, returning 0.0")
                return 0.0
            return left / right

        raise ExpressionError(f"Operator {type(node.op).__name__} not allowed")

    raise ExpressionError(
        f"AST node type {type(node).__name__} not allowed in expression"
    )
