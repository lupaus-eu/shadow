"""Safe parsing and evaluation for scenario-owned derived-metric formulas."""

import ast
import math
import re
from dataclasses import dataclass
from typing import cast

MAX_FORMULA_AST_DEPTH = 64
MAX_FORMULA_AST_NODES = 512


class FormulaError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedFormula:
    source: str
    tree: ast.Expression
    identifiers: tuple[str, ...]


def parse_formula(source: str) -> ParsedFormula:
    source = source.strip()
    if not source:
        raise FormulaError("Formula must not be blank.")
    if len(source) > 2000:
        raise FormulaError("Formula must be at most 2000 characters.")
    normalized = re.sub(r"(?<!\*)\^(?!\*)", "**", source)
    try:
        tree = ast.parse(normalized, mode="eval")
    except (RecursionError, SyntaxError) as error:
        raise FormulaError("Formula syntax is invalid.") from error
    _ensure_formula_tree_is_bounded(tree.body)
    identifiers: set[str] = set()
    _validate_node(tree.body, identifiers)
    if not identifiers:
        raise FormulaError("Formula must reference at least one timeserie short name.")
    return ParsedFormula(
        source=source, tree=tree, identifiers=tuple(sorted(identifiers))
    )


def _ensure_formula_tree_is_bounded(tree: ast.AST) -> None:
    nodes_seen = 0
    pending = [(tree, 1)]
    while pending:
        node, depth = pending.pop()
        nodes_seen += 1
        if nodes_seen > MAX_FORMULA_AST_NODES or depth > MAX_FORMULA_AST_DEPTH:
            raise FormulaError("Formula is too complex.")
        pending.extend((child, depth + 1) for child in ast.iter_child_nodes(node))


def evaluate_formula(parsed: ParsedFormula, values: dict[str, float]) -> float:
    result = _evaluate_node(parsed.tree.body, values)
    if not math.isfinite(result):
        raise FormulaError("Formula result is not finite.")
    return result


def _validate_node(node: ast.AST, identifiers: set[str]) -> None:
    if isinstance(node, ast.Name):
        identifiers.add(node.id)
        return
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise FormulaError("Formula literals must be finite numbers.")
        literal = node.value
        if not math.isfinite(float(literal)):
            raise FormulaError("Formula literals must be finite numbers.")
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        _validate_node(node.operand, identifiers)
        return
    if isinstance(node, ast.BinOp) and isinstance(
        node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
    ):
        _validate_node(node.left, identifiers)
        _validate_node(node.right, identifiers)
        return
    raise FormulaError("Formula contains an unsupported expression.")


def _evaluate_node(node: ast.AST, values: dict[str, float]) -> float:
    if isinstance(node, ast.Name):
        try:
            return values[node.id]
        except KeyError as error:
            raise FormulaError(f"Missing value for {node.id}.") from error
    if isinstance(node, ast.Constant):
        return float(cast(int | float, node.value))
    if isinstance(node, ast.UnaryOp):
        value = _evaluate_node(node.operand, values)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left = _evaluate_node(node.left, values)
        right = _evaluate_node(node.right, values)
        try:
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            return left**right
        except (ArithmeticError, OverflowError, ValueError) as error:
            raise FormulaError("Formula cannot be evaluated for this date.") from error
    raise FormulaError("Formula contains an unsupported expression.")
