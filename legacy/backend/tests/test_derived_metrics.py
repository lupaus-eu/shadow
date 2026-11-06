import pytest

from app.api.v1.org_states.derived_metrics import FormulaError, parse_formula


def test_parse_formula_rejects_excessive_ast_depth() -> None:
    formula = "+".join(["a"] * 1000)

    with pytest.raises(FormulaError, match="Formula is too complex."):
        parse_formula(formula)
