"""
pq-pytest: Test Power Query M code with pytest - no Excel required.

This package provides a Python testing framework for Power Query M language code,
allowing you to write tests for your M transforms using pytest and run them
against a standalone M runtime (no Excel or Power BI Desktop required).

Quick Start
-----------

1. Install the package from GitHub:

    pip install git+https://github.com/YOUR_USERNAME/pq-pytest.git

2. Install a Power Query runtime:
   
   - PowerQueryNet: https://github.com/gsimardnet/PowerQueryNet
   - Power Query SDK: VS Code extension 'powerquery.vscode-powerquery-sdk'

3. Write your M transform (transforms/my_transform.pq):

    let
        Source = Csv.Document(File.Contents([[InputPath]])),
        Result = Table.PromoteHeaders(Source)
    in
        Result

4. Write a test (tests/test_my_transform.py):

    def test_transform(pq_execute_file, pq_assert, tmp_path):
        input_file = tmp_path / "input.csv"
        input_file.write_text("a,b\\n1,2\\n")
        
        result = pq_execute_file(
            "transforms/my_transform.pq",
            input_files={"InputPath": input_file}
        )
        
        pq_assert.assert_success(result)
        pq_assert.assert_columns(result, ["a", "b"])

5. Run tests:

    pytest

CLI Usage
---------

The package also provides a CLI for running M code directly:

    # Check available runtimes
    pq check
    
    # Run M code from file
    pq run transforms/my_transform.pq -i InputPath data/input.csv
    
    # Run inline M code
    pq run -c "let x = 1 + 1 in x"
    
    # Create test scaffold
    pq scaffold my_transform

For more information, see the documentation at:
https://github.com/yourusername/pq-pytest

"""

from .runner import (
    MExecutionContext,
    MExecutionResult,
    MRunner,
    MockRunner,
    PowerQueryNetRunner,
    PQTestRunner,
    get_runner,
)
from .utils import (
    compare_tables,
    csv_to_m_table,
    dataframe_to_m_table,
    extract_m_inputs,
    generate_test_template,
    m_table_from_file,
    wrap_m_for_testing,
)

__version__ = "0.1.0"

__all__ = [
    # Core classes
    "MRunner",
    "MExecutionResult",
    "MExecutionContext",
    # Runner implementations
    "PowerQueryNetRunner",
    "PQTestRunner",
    "MockRunner",
    # Factory function
    "get_runner",
    # Utilities
    "dataframe_to_m_table",
    "csv_to_m_table",
    "m_table_from_file",
    "compare_tables",
    "generate_test_template",
    "extract_m_inputs",
    "wrap_m_for_testing",
]
