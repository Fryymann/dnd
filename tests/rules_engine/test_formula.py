import re

import pytest

from rules_engine.formula import FormulaError, evaluate_expression, referenced_names


def test_arithmetic():
    assert evaluate_expression("8 + 4 + 3", {}) == 15
    assert evaluate_expression("A * 2 - 1", {"A": 5}) == 9
    assert evaluate_expression("A / 2", {"A": 9}) == 4.5


def test_unary_minus():
    assert evaluate_expression("-A", {"A": 5}) == -5
    assert evaluate_expression("-(A + 1)", {"A": 5}) == -6


def test_float_literal():
    assert evaluate_expression("A + 0.5", {"A": 1}) == 1.5


def test_division_by_zero_raises():
    with pytest.raises(FormulaError, match="could not be evaluated"):
        evaluate_expression("A / 0", {"A": 1})


def test_allowed_functions():
    assert evaluate_expression("ceil(A / 2)", {"A": 9}) == 5
    assert evaluate_expression("floor(A / 2)", {"A": 9}) == 4
    assert evaluate_expression("min(A, 3)", {"A": 9}) == 3
    assert evaluate_expression("max(A, 3)", {"A": 9}) == 9


def test_attribute_access():
    assert evaluate_expression("CLASS_LEVEL.rogue", {"CLASS_LEVEL": {"rogue": 9}}) == 9


def test_attribute_access_on_non_dict_raises():
    with pytest.raises(FormulaError, match="does not support attribute access"):
        evaluate_expression("A.rogue", {"A": 5})


def test_missing_attribute_key_raises_by_name():
    """A missing key is not a value of zero — it is a fact the evaluator does not have.

    This reverses an earlier design decision (`container.get(node.attr, 0)`) that made a
    typo'd or unbound class name silently render as 0 — a plausible value for most of
    these variables, and therefore an invisible failure. A rogue formula evaluated for a
    character with no rogue levels correctly raises rather than returning 0: a verb is
    only bound to a character who holds it, so reaching a class the character lacks means
    the binding itself is wrong.
    """
    with pytest.raises(FormulaError, match=r"CLASS_LEVEL\.rogue is not defined"):
        evaluate_expression("CLASS_LEVEL.rogue", {"CLASS_LEVEL": {"fighter": 3}})
    with pytest.raises(FormulaError, match=r"CLASS_LEVEL\.rouge is not defined"):
        evaluate_expression("CLASS_LEVEL.rouge", {"CLASS_LEVEL": {"rogue": 9}})


def test_referenced_names_finds_plain_and_attribute_access():
    assert referenced_names("8 + SPELLCASTING_MOD + PROFICIENCY_BONUS") == {
        "SPELLCASTING_MOD",
        "PROFICIENCY_BONUS",
    }
    assert referenced_names("ceil(CLASS_LEVEL.rogue / 2)") == {"CLASS_LEVEL"}


def test_undefined_name_raises_by_name():
    with pytest.raises(NameError, match="MYSTERY"):
        evaluate_expression("MYSTERY + 1", {})


def test_function_name_used_as_bare_variable_is_rejected_by_both():
    """`referenced_names` must never accept an expression that `evaluate_expression`
    then handles differently. Before this was fixed, `referenced_names("min + 1")`
    returned an empty set (no declared dependency) while `evaluate_expression("min + 1",
    {"min": 5})` happily returned 6 — a dependency that was never declared. Reject the
    shape at parse time so the two functions cannot disagree."""
    with pytest.raises(ValueError, match="not allowed"):
        referenced_names("min + 1")
    with pytest.raises(ValueError, match="not allowed"):
        evaluate_expression("min + 1", {"min": 5})


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('rm -rf /')",
        "open('/etc/passwd').read()",
        "(1).__class__",
        "[x for x in range(10)]",
        "lambda: 1",
        "min(A, key=str)",
        "min(*A)",
        "f'{A}'",
        "A % 2",
        "A // 2",
        "+A",
    ],
)
def test_rejects_everything_that_is_not_arithmetic(expr):
    with pytest.raises(ValueError, match="not allowed"):
        evaluate_expression(expr, {"A": 1})


@pytest.mark.parametrize("expr", ["2 ** 3", "9**9**9"])
def test_rejects_exponentiation(expr):
    """`9**9**9` passes every other check and then hangs the process.

    CPython's bigint pow has no cutoff, so this is a denial of service in eight
    characters against whatever evaluates an authored formula. No D&D formula needs
    exponentiation, so the operator is simply not in the language.
    """
    with pytest.raises(ValueError, match="not allowed"):
        evaluate_expression(expr, {"A": 2})


def test_rejects_boolean_literals():
    with pytest.raises(ValueError, match="not allowed"):
        evaluate_expression("True + 1", {})


def test_rejects_malformed_syntax():
    with pytest.raises(FormulaError, match="not valid syntax"):
        evaluate_expression("A + ", {"A": 1})


def test_rejects_expression_over_length_limit():
    """A 3.9 MB formula of nothing but `*` burned 25.7s of CPU; on a billed, concurrent
    Cloud Function that is an outage. Reject by length before ast.parse ever runs."""
    huge = "1" + "*1" * 300
    with pytest.raises(FormulaError, match="exceeds 500 characters"):
        evaluate_expression(huge, {})


@pytest.mark.parametrize("expr", ["1e400", "1e400 - 1e400"])
def test_rejects_non_finite_literals(expr):
    """`1e400` is five characters that pass every other guard and produce `inf`;
    `1e400 - 1e400` produces `nan`. `nan` survives to output and `json.dumps` emits
    the bare token `NaN`, which is invalid JSON."""
    with pytest.raises(FormulaError, match="finite"):
        evaluate_expression(expr, {})


def test_rejects_non_finite_result_from_caller_supplied_values():
    """No non-finite literal appears in the formula text — the overflow only happens
    once caller-supplied values are multiplied together — so this can only be caught
    by validating the final result, not by inspecting literals."""
    with pytest.raises(FormulaError, match="finite"):
        evaluate_expression("A * A", {"A": 1e300})


@pytest.mark.parametrize(
    "values,expr,offending_key",
    [
        ({"A": "5"}, "A + 1", "A"),
        ({"A": [1, 2, 3]}, "A + 1", "A"),
        ({"A": True}, "A + 1", "A"),
        ({"A": float("inf")}, "A + 1", "A"),
        ({"CLASS_LEVEL": {"rogue": "9"}}, "CLASS_LEVEL.rogue", "CLASS_LEVEL.rogue"),
    ],
    ids=["string", "list", "bool", "inf", "dict-containing-a-string"],
)
def test_rejects_non_numeric_values_before_evaluating(values, expr, offending_key):
    """`values` is validated once, up front, rather than trusted and caught on the way
    out. This is what makes `"x" * 200000000` unreachable rather than merely rejected
    after allocating a 200 MB string: a string can never enter evaluation at all. It
    also closes the `bool` gap (`bool` subclasses `int`) without a special case in the
    arithmetic path itself. Each case must name the offending key, not just say
    "invalid"."""
    with pytest.raises(FormulaError, match=re.escape(offending_key)):
        evaluate_expression(expr, values)


def test_rejects_oversized_result():
    with pytest.raises(FormulaError, match="too large"):
        evaluate_expression("A * 3", {"A": 10**15})
