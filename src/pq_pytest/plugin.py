"""
Pytest plugin for Power Query M language testing.

This plugin provides:
- Fixtures for M code execution
- Custom markers for M tests
- Test collection for .pq files with .pqout expected outputs
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Generator

import pandas as pd
import pytest

from .runner import (
    MExecutionContext,
    MExecutionResult,
    MRunner,
    MockRunner,
    get_runner,
)


def pytest_addoption(parser):
    """Add command-line options for pq-pytest."""
    group = parser.getgroup("pq-pytest", "Power Query M testing options")
    
    group.addoption(
        "--pq-runner",
        action="store",
        default=None,
        choices=["pqnet", "pqtest", "mock"],
        help="Preferred M runtime to use (default: auto-detect)"
    )
    
    group.addoption(
        "--pq-timeout",
        action="store",
        default=60,
        type=int,
        help="Timeout in seconds for M code execution (default: 60)"
    )
    
    group.addoption(
        "--pq-collect",
        action="store_true",
        default=False,
        help="Collect and run .pq files as tests (requires matching .pqout files)"
    )


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "pq: mark test as a Power Query M test"
    )
    config.addinivalue_line(
        "markers", 
        "pq_slow: mark M test as slow (may be skipped with --pq-fast)"
    )


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def pq_runner(request) -> MRunner:
    """
    Session-scoped fixture providing the M runner.
    
    Usage:
        def test_my_m_code(pq_runner):
            result = pq_runner.execute('let x = 1 in x')
            assert result.success
    """
    preferred = request.config.getoption("--pq-runner")
    
    if preferred == "mock":
        return MockRunner()
    
    try:
        return get_runner(preferred)
    except RuntimeError as e:
        pytest.skip(str(e))


@pytest.fixture
def pq_context(request, tmp_path) -> MExecutionContext:
    """
    Fixture providing a fresh execution context for each test.
    
    The context includes a temporary working directory that's cleaned up
    after the test.
    
    Usage:
        def test_with_input_file(pq_runner, pq_context, tmp_path):
            # Write test input
            input_file = tmp_path / "input.csv"
            input_file.write_text("a,b\\n1,2\\n3,4")
            
            pq_context.input_files["InputPath"] = input_file
            
            result = pq_runner.execute(
                'let Source = Csv.Document(File.Contents([[InputPath]])) in Source',
                pq_context
            )
            assert result.success
    """
    timeout = request.config.getoption("--pq-timeout")
    return MExecutionContext(
        timeout_seconds=timeout,
        working_dir=tmp_path
    )


@pytest.fixture
def pq_mock_runner() -> MockRunner:
    """
    Fixture providing a mock runner for testing without a real runtime.
    
    Usage:
        def test_mock_example(pq_mock_runner):
            pq_mock_runner.set_response(
                "MyQuery",
                MExecutionResult(success=True, data=[{"col": "value"}])
            )
            result = pq_mock_runner.execute("let Source = MyQuery() in Source")
            assert result.data == [{"col": "value"}]
    """
    return MockRunner()


@pytest.fixture
def pq_execute(pq_runner, pq_context):
    """
    Convenience fixture that combines runner and context.
    
    Usage:
        def test_simple(pq_execute):
            result = pq_execute('let x = 1 + 1 in x')
            assert result.success
            assert result.data == [2]  # or similar
    """
    def _execute(m_code: str, **context_overrides) -> MExecutionResult:
        # Allow overriding context values
        for key, value in context_overrides.items():
            if hasattr(pq_context, key):
                setattr(pq_context, key, value)
            elif key == "input_files":
                pq_context.input_files.update(value)
            elif key == "parameters":
                pq_context.parameters.update(value)
        
        return pq_runner.execute(m_code, pq_context)
    
    return _execute


@pytest.fixture
def pq_execute_file(pq_runner, pq_context):
    """
    Fixture for executing .pq files.
    
    Usage:
        def test_from_file(pq_execute_file):
            result = pq_execute_file(Path("transforms/my_transform.pq"))
            assert result.success
    """
    def _execute_file(
        pq_file: Path | str, 
        **context_overrides
    ) -> MExecutionResult:
        pq_path = Path(pq_file)
        
        for key, value in context_overrides.items():
            if hasattr(pq_context, key):
                setattr(pq_context, key, value)
            elif key == "input_files":
                pq_context.input_files.update(value)
            elif key == "parameters":
                pq_context.parameters.update(value)
        
        return pq_runner.execute_file(pq_path, pq_context)
    
    return _execute_file


# ============================================================================
# Assertion Helpers
# ============================================================================

class PQAssertions:
    """Helper class for common M test assertions."""
    
    @staticmethod
    def assert_success(result: MExecutionResult, msg: str = None):
        """Assert that M execution succeeded."""
        if not result.success:
            error_info = result.error or "Unknown error"
            if result.error_line:
                error_info += f" (line {result.error_line})"
            pytest.fail(msg or f"M execution failed: {error_info}")
    
    @staticmethod
    def assert_row_count(result: MExecutionResult, expected: int, msg: str = None):
        """Assert the number of rows in the result."""
        PQAssertions.assert_success(result)
        actual = len(result.data or [])
        if actual != expected:
            pytest.fail(msg or f"Expected {expected} rows, got {actual}")
    
    @staticmethod
    def assert_columns(result: MExecutionResult, expected: list[str], msg: str = None):
        """Assert that the result has the expected columns."""
        PQAssertions.assert_success(result)
        if not result.data:
            pytest.fail(msg or "Result has no data")
        
        actual = set(result.data[0].keys())
        expected_set = set(expected)
        
        if actual != expected_set:
            missing = expected_set - actual
            extra = actual - expected_set
            parts = []
            if missing:
                parts.append(f"missing: {missing}")
            if extra:
                parts.append(f"extra: {extra}")
            pytest.fail(msg or f"Column mismatch: {', '.join(parts)}")
    
    @staticmethod
    def assert_dataframe_equal(
        result: MExecutionResult, 
        expected: pd.DataFrame,
        check_dtype: bool = False,
        check_exact: bool = False,
        **kwargs
    ):
        """Assert that the result matches an expected DataFrame."""
        PQAssertions.assert_success(result)
        actual = result.to_dataframe()
        
        pd.testing.assert_frame_equal(
            actual.reset_index(drop=True),
            expected.reset_index(drop=True),
            check_dtype=check_dtype,
            check_exact=check_exact,
            **kwargs
        )
    
    @staticmethod
    def assert_output_matches_file(
        result: MExecutionResult,
        expected_file: Path | str,
        format: str = "auto"
    ):
        """Assert that the result matches the content of an expected output file."""
        PQAssertions.assert_success(result)
        
        expected_path = Path(expected_file)
        if not expected_path.exists():
            pytest.fail(f"Expected output file not found: {expected_path}")
        
        # Detect format
        if format == "auto":
            suffix = expected_path.suffix.lower()
            format = {
                ".csv": "csv",
                ".json": "json",
                ".pqout": "pqout",
            }.get(suffix, "json")
        
        if format == "csv":
            expected_df = pd.read_csv(expected_path)
            PQAssertions.assert_dataframe_equal(result, expected_df)
        
        elif format == "json":
            expected_data = json.loads(expected_path.read_text())
            if isinstance(expected_data, dict):
                expected_data = [expected_data]
            assert result.data == expected_data
        
        elif format == "pqout":
            # PQTest's output format
            expected_data = json.loads(expected_path.read_text())
            assert result.data == expected_data


@pytest.fixture
def pq_assert() -> type[PQAssertions]:
    """
    Fixture providing assertion helpers.
    
    Usage:
        def test_with_assertions(pq_execute, pq_assert):
            result = pq_execute('let x = 1 in x')
            pq_assert.assert_success(result)
    """
    return PQAssertions


# ============================================================================
# Test Collection for .pq files
# ============================================================================

class PQTestFile(pytest.File):
    """Collector for .pq test files."""
    
    def collect(self) -> Generator[pytest.Item, None, None]:
        """Collect test items from a .pq file."""
        # Look for corresponding .pqout file
        pqout_path = self.path.with_suffix('.pqout')
        
        if pqout_path.exists():
            yield PQTestItem.from_parent(
                self, 
                name=self.path.stem,
                pq_path=self.path,
                pqout_path=pqout_path
            )


class PQTestItem(pytest.Item):
    """Test item for a single .pq file test."""
    
    def __init__(
        self, 
        name: str, 
        parent: PQTestFile,
        pq_path: Path,
        pqout_path: Path
    ):
        super().__init__(name, parent)
        self.pq_path = pq_path
        self.pqout_path = pqout_path
    
    def runtest(self):
        """Run the M code and compare to expected output."""
        # Get runner from session
        runner = get_runner()
        context = MExecutionContext()
        
        # Execute the M code
        result = runner.execute_file(self.pq_path, context)
        
        if not result.success:
            raise MTestError(f"M execution failed: {result.error}")
        
        # Load expected output
        expected = json.loads(self.pqout_path.read_text())
        
        # Compare
        if result.data != expected:
            raise MTestError(
                f"Output mismatch:\n"
                f"Expected: {json.dumps(expected, indent=2)}\n"
                f"Actual: {json.dumps(result.data, indent=2)}"
            )
    
    def repr_failure(self, excinfo):
        """Return a representation of a test failure."""
        if isinstance(excinfo.value, MTestError):
            return str(excinfo.value)
        return super().repr_failure(excinfo)
    
    def reportinfo(self):
        return self.path, None, f"pq: {self.name}"


class MTestError(Exception):
    """Custom exception for M test failures."""
    pass


def pytest_collect_file(parent, file_path: Path):
    """Hook to collect .pq files as tests."""
    if parent.config.getoption("--pq-collect"):
        if file_path.suffix == ".pq" and not file_path.name.endswith(".query.pq"):
            # Only collect if there's a matching .pqout file
            pqout = file_path.with_suffix('.pqout')
            if pqout.exists():
                return PQTestFile.from_parent(parent, path=file_path)
    return None
