"""sp_validator 断言求值器与数据模型测试."""
import pytest

from agent.sp_validator import (
    safe_eval_assertion,
    AssertionEvalError,
    CheckResult,
    ValidationReport,
)


class TestSafeEvalAssertion:
    def test_simple_equality(self):
        assert safe_eval_assertion("cnt == 0", {"cnt": 0}) is True
        assert safe_eval_assertion("cnt == 0", {"cnt": 3}) is False

    def test_arithmetic_with_functions(self):
        assert safe_eval_assertion(
            "abs(a - b) / b < 0.01", {"a": 100.0, "b": 100.5}
        ) is True
        assert safe_eval_assertion(
            "abs(a - b) / b < 0.01", {"a": 100.0, "b": 200.0}
        ) is False

    def test_boolean_and_or(self):
        assert safe_eval_assertion(
            "d - c == 0 and cnt > 0", {"d": 50, "c": 50, "cnt": 3}
        ) is True
        assert safe_eval_assertion(
            "x < 0 or x > 100", {"x": 150}
        ) is True

    def test_chained_comparison(self):
        assert safe_eval_assertion("0 < x < 100", {"x": 50}) is True
        assert safe_eval_assertion("0 < x < 100", {"x": 150}) is False

    def test_unknown_variable_rejected(self):
        with pytest.raises(AssertionEvalError):
            safe_eval_assertion("unknown_col > 0", {"cnt": 1})

    def test_import_rejected(self):
        with pytest.raises(AssertionEvalError):
            safe_eval_assertion("__import__('os')", {"x": 1})

    def test_attribute_access_rejected(self):
        with pytest.raises(AssertionEvalError):
            safe_eval_assertion("x.__class__", {"x": 1})

    def test_disallowed_function_rejected(self):
        with pytest.raises(AssertionEvalError):
            safe_eval_assertion("open('/etc/passwd')", {"x": 1})

    def test_syntax_error_rejected(self):
        with pytest.raises(AssertionEvalError):
            safe_eval_assertion("cnt ==", {"cnt": 1})


class TestValidationReport:
    def test_counts(self):
        report = ValidationReport(
            sp_name="SP_TEST",
            results=[
                CheckResult("c1", "", "对账", "error", True, "cnt==0"),
                CheckResult("c2", "", "对账", "error", False, "x>0"),
                CheckResult("c3", "", "合理性", "warning", False, "y>0"),
            ],
        )
        assert report.total == 3
        assert report.passed == 1
        assert report.failed == 2

    def test_has_error_failures_true(self):
        report = ValidationReport(
            sp_name="SP_TEST",
            results=[CheckResult("c1", "", "对账", "error", False, "x>0")],
        )
        assert report.has_error_failures is True

    def test_has_error_failures_false_when_only_warning_fails(self):
        report = ValidationReport(
            sp_name="SP_TEST",
            results=[CheckResult("c1", "", "合理性", "warning", False, "y>0")],
        )
        assert report.has_error_failures is False
