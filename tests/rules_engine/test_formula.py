import pytest

from rules_engine.formula import evaluate_expression, referenced_names


def test_arithmetic():
    assert evaluate_expression("8 + 4 + 3", {}) == 15
    assert evaluate_expression("A * 2 - 1", {"A": 5}) == 9
    assert evaluate_expression("A / 2", {"A": 9}) == 4.5


def test_allowed_functions():
    assert evaluate_expression("ceil(A / 2)", {"A": 9}) == 5
    assert evaluate_expression("floor(A / 2)", {"A": 9}) == 4
    assert evaluate_expression("min(A, 3)", {"A": 9}) == 3
    assert evaluate_expression("max(A, 3)", {"A": 9}) == 9


def test_subscripted_variable():
    assert evaluate_expression("CLASS_LEVEL.rogue", {"CLASS_LEVEL": {"rogue": 9}}) == 9


def test_referenced_names_finds_plain_and_subscripted():
    assert referenced_names("8 + SPELLCASTING_MOD + PROFICIENCY_BONUS") == {
        "SPELLCASTING_MOD",
        "PROFICIENCY_BONUS",
    }
    assert referenced_names("ceil(CLASS_LEVEL.rogue / 2)") == {"CLASS_LEVEL"}


def test_undefined_name_raises_by_name():
    with pytest.raises(NameError, match="MYSTERY"):
        evaluate_expression("MYSTERY + 1", {})


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('rm -rf /')",
        "open('/etc/passwd').read()",
        "(1).__class__",
        "[x for x in range(10)]",
        "lambda: 1",
    ],
)
def test_rejects_everything_that_is_not_arithmetic(expr):
    with pytest.raises(ValueError, match="not allowed"):
        evaluate_expression(expr, {})
