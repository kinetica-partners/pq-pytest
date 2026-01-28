"""
Tests for the pq-pytest package itself.

These tests verify that the library works correctly, using the mock runner
so they can run without an M runtime installed.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from pq_pytest import (
    MExecutionContext,
    MExecutionResult,
    MockRunner,
    PowerQueryNetRunner,
    compare_tables,
    csv_to_m_table,
    dataframe_to_m_table,
    extract_m_inputs,
    wrap_m_for_testing,
)


class TestMExecutionResult:
    """Tests for MExecutionResult."""

    def test_success_result(self):
        result = MExecutionResult(
            success=True,
            data=[{"a": 1, "b": 2}]
        )
        assert result.success
        assert result.data == [{"a": 1, "b": 2}]
        assert result.error is None

    def test_failure_result(self):
        result = MExecutionResult(
            success=False,
            error="Something went wrong",
            error_line=10,
            error_column=5
        )
        assert not result.success
        assert result.error == "Something went wrong"
        assert result.error_line == 10
        assert result.error_column == 5

    def test_to_dataframe(self):
        result = MExecutionResult(
            success=True,
            data=[
                {"a": 1, "b": "x"},
                {"a": 2, "b": "y"}
            ]
        )
        df = result.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert list(df.columns) == ["a", "b"]

    def test_to_dataframe_raises_on_failure(self):
        result = MExecutionResult(success=False, error="Failed")
        with pytest.raises(ValueError, match="Cannot convert failed result"):
            result.to_dataframe()


class TestMExecutionContext:
    """Tests for MExecutionContext."""

    def test_default_context(self):
        ctx = MExecutionContext()
        assert ctx.input_files == {}
        assert ctx.parameters == {}
        assert ctx.timeout_seconds == 60
        assert ctx.working_dir is None

    def test_context_with_values(self, tmp_path):
        ctx = MExecutionContext(
            input_files={"InputPath": tmp_path / "data.csv"},
            parameters={"Threshold": 100},
            timeout_seconds=120,
            working_dir=tmp_path
        )
        assert "InputPath" in ctx.input_files
        assert ctx.parameters["Threshold"] == 100
        assert ctx.timeout_seconds == 120
        assert ctx.working_dir == tmp_path


class TestMockRunner:
    """Tests for MockRunner."""

    def test_is_available(self):
        runner = MockRunner()
        assert runner.is_available()

    def test_default_response(self):
        runner = MockRunner()
        result = runner.execute("let x = 1 in x")
        assert result.success
        assert result.data == []

    def test_custom_response(self):
        runner = MockRunner()
        runner.set_response(
            "MyQuery",
            MExecutionResult(success=True, data=[{"col": "value"}])
        )
        
        result = runner.execute("let Source = MyQuery() in Source")
        assert result.success
        assert result.data == [{"col": "value"}]

    def test_call_logging(self):
        runner = MockRunner()
        ctx = MExecutionContext(parameters={"x": 1})
        
        runner.execute("let a = 1 in a", ctx)
        runner.execute("let b = 2 in b")
        
        assert len(runner.call_log) == 2
        assert "a = 1" in runner.call_log[0][0]
        assert runner.call_log[0][1] == ctx

    def test_execute_file(self, tmp_path):
        runner = MockRunner()
        runner.set_response("test", MExecutionResult(success=True, data=[{"x": 1}]))
        
        pq_file = tmp_path / "test.pq"
        pq_file.write_text("let test = 1 in test")
        
        result = runner.execute_file(pq_file)
        assert result.success


class TestPowerQueryNetRunner:
    """Tests for PowerQueryNetRunner (without actual execution)."""

    def test_not_available_without_install(self):
        # This test verifies behavior when pqnet isn't installed
        runner = PowerQueryNetRunner(pqnet_path="/nonexistent/path/pqnet")
        assert not runner.is_available()

    def test_prepare_m_code_bracket_syntax(self):
        runner = PowerQueryNetRunner()
        ctx = MExecutionContext(input_files={"InputPath": Path("/data/input.csv")})
        code = 'let Source = File.Contents([[InputPath]]) in Source'
        prepared = runner._prepare_m_code(code, ctx)
        # Check placeholder was replaced (path format varies by OS)
        assert "[[InputPath]]" not in prepared
        assert "input.csv" in prepared

    def test_prepare_m_code_hash_syntax(self):
        runner = PowerQueryNetRunner()
        ctx = MExecutionContext(input_files={"InputPath": Path("/data/input.csv")})
        code = 'let Source = File.Contents(#"InputPath") in Source'
        prepared = runner._prepare_m_code(code, ctx)
        # Check placeholder was replaced (path format varies by OS)
        assert '#"InputPath"' not in prepared
        assert "input.csv" in prepared

    def test_prepare_m_code_parameters(self):
        runner = PowerQueryNetRunner()
        ctx = MExecutionContext(parameters={
            "Threshold": 100,
            "Name": "test",
            "Active": True
        })
        
        code = 'let x = [[Threshold]], y = [[Name]], z = [[Active]] in x'
        prepared = runner._prepare_m_code(code, ctx)
        
        assert "100" in prepared
        assert '"test"' in prepared
        assert "true" in prepared


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_dataframe_to_m_table(self):
        df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        result = dataframe_to_m_table(df)
        
        assert "#table(" in result
        assert '"a"' in result
        assert '"b"' in result
        assert "{1, " in result
        assert '"x"' in result

    def test_dataframe_to_m_table_with_nulls(self):
        df = pd.DataFrame({"a": [1, None], "b": ["x", None]})
        result = dataframe_to_m_table(df)
        
        assert "null" in result

    def test_csv_to_m_table(self):
        csv_content = "a,b\n1,x\n2,y"
        result = csv_to_m_table(csv_content)
        
        assert "#table(" in result
        assert '"a"' in result

    def test_compare_tables_equal(self):
        actual = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
        expected = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
        
        is_equal, error = compare_tables(actual, expected)
        assert is_equal
        assert error is None

    def test_compare_tables_different_rows(self):
        actual = [{"a": 1}]
        expected = [{"a": 1}, {"a": 2}]
        
        is_equal, error = compare_tables(actual, expected)
        assert not is_equal
        assert "Row count" in error

    def test_compare_tables_different_values(self):
        actual = [{"a": 1}]
        expected = [{"a": 2}]
        
        is_equal, error = compare_tables(actual, expected)
        assert not is_equal
        assert "Value mismatch" in error

    def test_compare_tables_ignore_order(self):
        actual = [{"a": 2}, {"a": 1}]
        expected = [{"a": 1}, {"a": 2}]
        
        is_equal, _ = compare_tables(actual, expected, ignore_order=True)
        assert is_equal

    def test_compare_tables_ignore_columns(self):
        actual = [{"a": 1, "b": "different"}]
        expected = [{"a": 1, "b": "original"}]
        
        is_equal, _ = compare_tables(actual, expected, ignore_columns=["b"])
        assert is_equal

    def test_extract_m_inputs_bracket_syntax(self):
        code = """
        let
            Source = File.Contents([[InputPath]]),
            Other = [[OutputPath]]
        in
            Source
        """
        inputs = extract_m_inputs(code)
        assert "InputPath" in inputs
        assert "OutputPath" in inputs

    def test_wrap_m_for_testing_let_expression(self):
        code = """let
    Source = File.Contents([[InputPath]])
in
    Source"""
        
        wrapped = wrap_m_for_testing(code, {"InputPath": "/data/test.csv"})
        
        assert 'InputPath = "/data/test.csv"' in wrapped
        assert "let" in wrapped
        assert "in" in wrapped


class TestPytestPlugin:
    """Tests for pytest plugin fixtures."""

    def test_pq_mock_runner_fixture(self, pq_mock_runner):
        """Test that pq_mock_runner fixture works."""
        assert isinstance(pq_mock_runner, MockRunner)
        assert pq_mock_runner.is_available()

    def test_pq_context_fixture(self, pq_context, tmp_path):
        """Test that pq_context fixture provides working context."""
        assert isinstance(pq_context, MExecutionContext)
        # The fixture sets working_dir to tmp_path
        assert pq_context.working_dir == tmp_path


class TestAssertions:
    """Tests for assertion helpers."""

    def test_assert_success_passes(self, pq_assert):
        result = MExecutionResult(success=True, data=[])
        # Should not raise
        pq_assert.assert_success(result)

    def test_assert_success_fails(self, pq_assert):
        result = MExecutionResult(success=False, error="Test error")
        with pytest.raises(pytest.fail.Exception, match="Test error"):
            pq_assert.assert_success(result)

    def test_assert_row_count_passes(self, pq_assert):
        result = MExecutionResult(success=True, data=[{"a": 1}, {"a": 2}])
        pq_assert.assert_row_count(result, 2)

    def test_assert_row_count_fails(self, pq_assert):
        result = MExecutionResult(success=True, data=[{"a": 1}])
        with pytest.raises(pytest.fail.Exception, match="Expected 2 rows"):
            pq_assert.assert_row_count(result, 2)

    def test_assert_columns_passes(self, pq_assert):
        result = MExecutionResult(success=True, data=[{"a": 1, "b": 2}])
        pq_assert.assert_columns(result, ["a", "b"])

    def test_assert_columns_fails_missing(self, pq_assert):
        result = MExecutionResult(success=True, data=[{"a": 1}])
        with pytest.raises(pytest.fail.Exception, match="missing"):
            pq_assert.assert_columns(result, ["a", "b"])
