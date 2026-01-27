"""
Utility functions for Power Query M testing.

Includes helpers for:
- Data serialization and comparison
- M code templating
- Common data transformations
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

import pandas as pd


def dataframe_to_m_table(df: pd.DataFrame) -> str:
    """
    Convert a pandas DataFrame to M table literal syntax.
    
    This is useful for generating inline test data in M code.
    
    Example:
        >>> df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        >>> print(dataframe_to_m_table(df))
        #table(
            {"a", "b"},
            {
                {1, "x"},
                {2, "y"}
            }
        )
    """
    columns = list(df.columns)
    columns_m = "{" + ", ".join(f'"{c}"' for c in columns) + "}"
    
    rows = []
    for _, row in df.iterrows():
        values = []
        for col in columns:
            val = row[col]
            if pd.isna(val):
                values.append("null")
            elif isinstance(val, str):
                # Escape quotes in strings
                escaped = val.replace('"', '""')
                values.append(f'"{escaped}"')
            elif isinstance(val, bool):
                values.append("true" if val else "false")
            elif isinstance(val, (int, float)):
                values.append(str(val))
            else:
                values.append(f'"{val}"')
        rows.append("{" + ", ".join(values) + "}")
    
    rows_m = "{\n            " + ",\n            ".join(rows) + "\n        }"
    
    return f"#table(\n        {columns_m},\n        {rows_m}\n    )"


def csv_to_m_table(csv_content: str) -> str:
    """
    Convert CSV content to M table literal syntax.
    
    Example:
        >>> csv_data = "a,b\\n1,x\\n2,y"
        >>> print(csv_to_m_table(csv_data))
    """
    df = pd.read_csv(io.StringIO(csv_content))
    return dataframe_to_m_table(df)


def m_table_from_file(file_path: Path | str) -> str:
    """
    Read a CSV file and convert to M table literal.
    
    This is useful for embedding test data directly in M code.
    """
    df = pd.read_csv(file_path)
    return dataframe_to_m_table(df)


def compare_tables(
    actual: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    ignore_order: bool = False,
    ignore_columns: list[str] | None = None,
    rtol: float = 1e-5,
    atol: float = 1e-8,
) -> tuple[bool, str | None]:
    """
    Compare two table results with flexible comparison options.
    
    Args:
        actual: Actual result data
        expected: Expected result data
        ignore_order: If True, compare as sets (order doesn't matter)
        ignore_columns: Columns to exclude from comparison
        rtol: Relative tolerance for float comparison
        atol: Absolute tolerance for float comparison
    
    Returns:
        Tuple of (is_equal, error_message)
    """
    if ignore_columns:
        actual = [
            {k: v for k, v in row.items() if k not in ignore_columns}
            for row in actual
        ]
        expected = [
            {k: v for k, v in row.items() if k not in ignore_columns}
            for row in expected
        ]
    
    if len(actual) != len(expected):
        return False, f"Row count mismatch: {len(actual)} vs {len(expected)}"
    
    if ignore_order:
        # Convert to comparable form (sort by all values)
        def row_key(row):
            return tuple(sorted(row.items()))
        actual_sorted = sorted(actual, key=row_key)
        expected_sorted = sorted(expected, key=row_key)
    else:
        actual_sorted = actual
        expected_sorted = expected
    
    for i, (act_row, exp_row) in enumerate(zip(actual_sorted, expected_sorted)):
        if set(act_row.keys()) != set(exp_row.keys()):
            return False, f"Column mismatch in row {i}: {set(act_row.keys())} vs {set(exp_row.keys())}"
        
        for col in act_row:
            act_val = act_row[col]
            exp_val = exp_row[col]
            
            # Handle None/null
            if act_val is None and exp_val is None:
                continue
            if act_val is None or exp_val is None:
                return False, f"Null mismatch in row {i}, column '{col}': {act_val} vs {exp_val}"
            
            # Handle numeric comparison with tolerance
            if isinstance(act_val, (int, float)) and isinstance(exp_val, (int, float)):
                if not _floats_equal(act_val, exp_val, rtol, atol):
                    return False, f"Value mismatch in row {i}, column '{col}': {act_val} vs {exp_val}"
            elif act_val != exp_val:
                return False, f"Value mismatch in row {i}, column '{col}': {act_val!r} vs {exp_val!r}"
    
    return True, None


def _floats_equal(a: float, b: float, rtol: float, atol: float) -> bool:
    """Check if two floats are approximately equal."""
    return abs(a - b) <= atol + rtol * abs(b)


def generate_test_template(
    transform_name: str,
    input_columns: list[str],
    output_columns: list[str] | None = None,
) -> str:
    """
    Generate a Python test template for an M transform.
    
    Args:
        transform_name: Name of the transform (e.g., "clean_inventory")
        input_columns: Expected input columns
        output_columns: Expected output columns (defaults to input_columns)
    
    Returns:
        Python test file content as a string
    """
    output_columns = output_columns or input_columns
    
    input_cols_str = ", ".join(f'"{c}"' for c in input_columns)
    output_cols_str = ", ".join(f'"{c}"' for c in output_columns)
    
    return f'''"""Tests for {transform_name} transform."""

from pathlib import Path

import pandas as pd
import pytest


TRANSFORMS_DIR = Path(__file__).parent.parent / "transforms"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class Test{transform_name.title().replace("_", "")}:
    """Tests for the {transform_name} transform."""
    
    @pytest.fixture
    def sample_input(self, tmp_path) -> Path:
        """Create sample input data."""
        data = {{
            {", ".join(f'"{c}": []' for c in input_columns)}
        }}
        df = pd.DataFrame(data)
        path = tmp_path / "input.csv"
        df.to_csv(path, index=False)
        return path
    
    def test_produces_expected_columns(
        self,
        pq_execute_file,
        pq_assert,
        sample_input
    ):
        """Transform should produce expected output columns."""
        result = pq_execute_file(
            TRANSFORMS_DIR / "{transform_name}.pq",
            input_files={{"InputPath": sample_input}}
        )
        
        pq_assert.assert_success(result)
        pq_assert.assert_columns(result, [{output_cols_str}])
    
    def test_handles_empty_input(
        self,
        pq_execute_file,
        pq_assert,
        tmp_path
    ):
        """Transform should handle empty input."""
        empty = tmp_path / "empty.csv"
        empty.write_text("{",".join(input_columns)}\\n")
        
        result = pq_execute_file(
            TRANSFORMS_DIR / "{transform_name}.pq",
            input_files={{"InputPath": empty}}
        )
        
        pq_assert.assert_success(result)
        pq_assert.assert_row_count(result, 0)
'''


def extract_m_inputs(m_code: str) -> list[str]:
    """
    Extract input placeholders from M code.
    
    Looks for patterns like:
    - [[InputPath]]
    - #"InputPath"
    - File.Contents([[...]])
    
    Returns:
        List of input names found
    """
    import re
    
    inputs = set()
    
    # Match [[Name]] pattern
    for match in re.finditer(r'\[\[(\w+)\]\]', m_code):
        inputs.add(match.group(1))
    
    # Match #"Name" pattern (excluding standard M identifiers)
    for match in re.finditer(r'#"(\w+)"', m_code):
        name = match.group(1)
        # Filter out common M step names
        if name not in {'Promoted Headers', 'Changed Type', 'Removed Columns'}:
            if 'Path' in name or 'File' in name or 'Source' in name:
                inputs.add(name)
    
    return list(inputs)


def wrap_m_for_testing(m_code: str, inputs: dict[str, str]) -> str:
    """
    Wrap M code with input bindings for testing.
    
    This creates a wrapper that defines the input values as let bindings
    before the actual transform code.
    
    Args:
        m_code: Original M code
        inputs: Dictionary of input name -> value/path
    
    Returns:
        Wrapped M code
    """
    # If the code is a let expression, we need to merge
    m_code_stripped = m_code.strip()
    
    if m_code_stripped.lower().startswith('let'):
        # Find the 'in' keyword
        import re
        match = re.search(r'\bin\b', m_code_stripped, re.IGNORECASE)
        if match:
            let_section = m_code_stripped[3:match.start()].strip()
            in_section = m_code_stripped[match.end():].strip()
            
            # Add our bindings at the start
            bindings = []
            for name, value in inputs.items():
                if isinstance(value, str) and not value.startswith('"'):
                    value = f'"{value}"'
                bindings.append(f'    {name} = {value}')
            
            bindings_str = ",\n".join(bindings)
            if bindings_str:
                bindings_str += ","
            
            return f"let\n{bindings_str}\n{let_section}\nin\n{in_section}"
    
    # Otherwise, create a new let expression
    bindings = []
    for name, value in inputs.items():
        if isinstance(value, str) and not value.startswith('"'):
            value = f'"{value}"'
        bindings.append(f'    {name} = {value}')
    
    bindings_str = ",\n".join(bindings)
    
    return f"let\n{bindings_str},\n    __result__ = ({m_code})\nin\n    __result__"
