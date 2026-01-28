"""
Command-line interface for pq-pytest.

Provides commands for:
- Running M code directly
- Checking runtime availability
- Creating test scaffolds
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from .runner import (
    MExecutionContext,
    MExecutionResult,
    MockRunner,
    PowerQueryNetRunner,
    PQTestRunner,
    get_runner,
)


@click.group()
@click.version_option()
def main():
    """Power Query M language testing tools."""
    pass


@main.command()
@click.argument("input", type=click.Path(exists=True), required=False)
@click.option(
    "-c", "--code",
    help="M code to execute (alternative to file input)"
)
@click.option(
    "-o", "--output",
    type=click.Choice(["json", "csv", "table", "raw"]),
    default="json",
    help="Output format (default: json)"
)
@click.option(
    "-i", "--input-file",
    multiple=True,
    type=(str, click.Path(exists=True)),
    help="Input file mapping: NAME PATH (can be repeated)"
)
@click.option(
    "-p", "--param",
    multiple=True,
    type=(str, str),
    help="Parameter: NAME VALUE (can be repeated)"
)
@click.option(
    "--timeout",
    default=60,
    type=int,
    help="Execution timeout in seconds"
)
@click.option(
    "--runner",
    type=click.Choice(["auto", "pqnet", "pqtest"]),
    default="auto",
    help="M runtime to use"
)
@click.option(
    "-v", "--verbose",
    is_flag=True,
    help="Verbose output"
)
def run(input, code, output, input_file, param, timeout, runner, verbose):
    """
    Execute Power Query M code.
    
    Examples:
    
        # Run M code from file
        pq run transforms/clean_data.pq
        
        # Run inline M code
        pq run -c "let x = 1 + 1 in x"
        
        # Run with input file
        pq run transform.pq -i InputPath data/input.csv
        
        # Run with parameters
        pq run transform.pq -p FilterValue 100
    """
    # Get M code
    if code:
        m_code = code
        source_name = "<inline>"
    elif input:
        m_code = Path(input).read_text(encoding='utf-8')
        source_name = input
    else:
        raise click.UsageError("Either INPUT file or --code must be provided")
    
    # Set up context
    context = MExecutionContext(timeout_seconds=timeout)
    
    for name, path in input_file:
        context.input_files[name] = Path(path)
    
    for name, value in param:
        # Try to parse as number/bool
        try:
            context.parameters[name] = int(value)
        except ValueError:
            try:
                context.parameters[name] = float(value)
            except ValueError:
                if value.lower() in ('true', 'false'):
                    context.parameters[name] = value.lower() == 'true'
                else:
                    context.parameters[name] = value
    
    # Get runner
    try:
        if runner == "auto":
            m_runner = get_runner()
        elif runner == "pqnet":
            m_runner = PowerQueryNetRunner()
        else:
            m_runner = PQTestRunner()
        
        if not m_runner.is_available():
            click.echo(f"Error: {runner} runtime not available", err=True)
            sys.exit(1)
            
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    
    if verbose:
        click.echo(f"Using runner: {type(m_runner).__name__}", err=True)
        click.echo(f"Source: {source_name}", err=True)
    
    # Execute
    result = m_runner.execute(m_code, context)
    
    # Output
    if not result.success:
        error_info = {"success": False, "error": result.error}
        if result.error_line:
            error_info["line"] = result.error_line
        if result.error_column:
            error_info["column"] = result.error_column
        
        if output == "json":
            click.echo(json.dumps(error_info, indent=2))
        else:
            click.echo(f"Error: {result.error}", err=True)
            if result.error_line:
                click.echo(f"  at line {result.error_line}", err=True)
        sys.exit(1)
    
    # Success output
    if output == "json":
        output_data = {
            "success": True,
            "data": result.data,
        }
        click.echo(json.dumps(output_data, indent=2))
    
    elif output == "csv":
        import pandas as pd
        df = result.to_dataframe()
        click.echo(df.to_csv(index=False))
    
    elif output == "table":
        import pandas as pd
        df = result.to_dataframe()
        click.echo(df.to_string(index=False))
    
    elif output == "raw":
        click.echo(result.raw_output)


@main.command()
def check():
    """
    Check which M runtimes are available.
    
    Useful for debugging setup issues.
    """
    click.echo("Checking Power Query runtimes...\n")
    
    # Check PowerQueryNet
    pqnet = PowerQueryNetRunner()
    if pqnet.is_available():
        click.echo("✓ PowerQueryNet (pqnet): Available")
        click.echo(f"  Path: {pqnet.pqnet_path}")
    else:
        click.echo("✗ PowerQueryNet (pqnet): Not found")
        click.echo("  Install from: https://github.com/gsimardnet/PowerQueryNet")
    
    click.echo()
    
    # Check PQTest
    pqtest = PQTestRunner()
    if pqtest.is_available():
        click.echo("✓ PQTest.exe: Available")
        click.echo(f"  Path: {pqtest.pqtest_path}")
    else:
        click.echo("✗ PQTest.exe: Not found")
        click.echo("  Install Power Query SDK VS Code extension")
    
    click.echo()
    
    # Summary
    try:
        runner = get_runner()
        click.echo(f"Default runner: {type(runner).__name__}")
    except RuntimeError:
        click.echo("No runtime available!")
        click.echo("\nTo use pq-pytest, install one of the runtimes above.")
        sys.exit(1)


@main.command()
@click.argument("name")
@click.option(
    "--dir", "-d",
    type=click.Path(),
    default=".",
    help="Directory to create files in"
)
def scaffold(name, dir):
    """
    Create a new M transform with test scaffold.
    
    Creates:
    - transforms/<name>.pq - The M code file
    - tests/test_<name>.py - Python test file
    - tests/fixtures/<name>_input.csv - Sample input
    - tests/fixtures/<name>_expected.csv - Expected output
    
    Example:
    
        pq scaffold clean_inventory
    """
    base_dir = Path(dir)
    
    # Create directories
    transforms_dir = base_dir / "transforms"
    tests_dir = base_dir / "tests"
    fixtures_dir = tests_dir / "fixtures"
    
    transforms_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    
    # Create M file
    pq_file = transforms_dir / f"{name}.pq"
    pq_content = f'''// {name}.pq
// Power Query M transform
//
// Input: [[InputPath]] - CSV file path
// Output: Transformed table

let
    // Load input data
    Source = Csv.Document(
        File.Contents([[InputPath]]),
        [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.None]
    ),
    
    // Promote headers
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    
    // Add your transformations here
    Result = PromotedHeaders
in
    Result
'''
    pq_file.write_text(pq_content)
    click.echo(f"Created: {pq_file}")
    
    # Create input fixture
    input_file = fixtures_dir / f"{name}_input.csv"
    input_content = '''id,name,value
1,alpha,100
2,beta,200
3,gamma,300
'''
    input_file.write_text(input_content)
    click.echo(f"Created: {input_file}")
    
    # Create expected output fixture
    expected_file = fixtures_dir / f"{name}_expected.csv"
    expected_content = '''id,name,value
1,alpha,100
2,beta,200
3,gamma,300
'''
    expected_file.write_text(expected_content)
    click.echo(f"Created: {expected_file}")
    
    # Create Python test file
    test_file = tests_dir / f"test_{name}.py"
    test_content = f'''"""Tests for {name} transform."""

from pathlib import Path

import pandas as pd
import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"
TRANSFORMS_DIR = Path(__file__).parent.parent / "transforms"


class Test{name.title().replace("_", "")}:
    """Tests for the {name} transform."""
    
    @pytest.fixture
    def input_data(self, tmp_path):
        """Load test input data."""
        input_file = FIXTURES_DIR / "{name}_input.csv"
        # Copy to temp dir so the transform can access it
        temp_input = tmp_path / "input.csv"
        temp_input.write_text(input_file.read_text())
        return temp_input
    
    @pytest.fixture
    def expected_data(self):
        """Load expected output data."""
        return pd.read_csv(FIXTURES_DIR / "{name}_expected.csv")
    
    def test_transform_produces_expected_output(
        self, 
        pq_execute_file, 
        pq_assert,
        input_data,
        expected_data
    ):
        """The transform should produce the expected output."""
        result = pq_execute_file(
            TRANSFORMS_DIR / "{name}.pq",
            input_files={{"InputPath": input_data}}
        )
        
        pq_assert.assert_success(result)
        pq_assert.assert_dataframe_equal(result, expected_data)
    
    def test_transform_has_expected_columns(
        self,
        pq_execute_file,
        pq_assert,
        input_data
    ):
        """The transform should have the expected columns."""
        result = pq_execute_file(
            TRANSFORMS_DIR / "{name}.pq",
            input_files={{"InputPath": input_data}}
        )
        
        pq_assert.assert_success(result)
        pq_assert.assert_columns(result, ["id", "name", "value"])
    
    def test_transform_handles_empty_input(
        self,
        pq_execute_file,
        pq_assert,
        tmp_path
    ):
        """The transform should handle empty input gracefully."""
        empty_input = tmp_path / "empty.csv"
        empty_input.write_text("id,name,value\\n")
        
        result = pq_execute_file(
            TRANSFORMS_DIR / "{name}.pq",
            input_files={{"InputPath": empty_input}}
        )
        
        pq_assert.assert_success(result)
        pq_assert.assert_row_count(result, 0)
'''
    test_file.write_text(test_content)
    click.echo(f"Created: {test_file}")
    
    # Create conftest.py if it doesn't exist
    conftest_file = tests_dir / "conftest.py"
    if not conftest_file.exists():
        conftest_content = '''"""Pytest configuration for M transform tests."""

# The pq-pytest plugin provides fixtures automatically when installed.
# If you need custom fixtures, add them here.

# Example: Skip all tests if no M runtime is available
# import pytest
# from pq_pytest.runner import get_runner
#
# def pytest_configure(config):
#     try:
#         get_runner()
#     except RuntimeError:
#         pytest.skip("No M runtime available", allow_module_level=True)
'''
        conftest_file.write_text(conftest_content)
        click.echo(f"Created: {conftest_file}")
    
    click.echo(f"\nScaffold created for '{name}'!")
    click.echo("\nNext steps:")
    click.echo(f"  1. Edit transforms/{name}.pq with your M code")
    click.echo(f"  2. Update tests/fixtures/{name}_input.csv with test data")
    click.echo(f"  3. Update tests/fixtures/{name}_expected.csv with expected output")
    click.echo(f"  4. Run: pytest tests/test_{name}.py")


@main.command()
@click.argument("pq_file", type=click.Path(exists=True))
@click.option(
    "--output", "-o",
    type=click.Path(),
    help="Output file path (default: <input>.pqout)"
)
def snapshot(pq_file, output):
    """
    Generate a .pqout snapshot file from M code execution.
    
    This runs the M code and saves the output as the expected result
    for future regression testing.
    
    Example:
    
        pq snapshot transforms/my_transform.pq
    """
    pq_path = Path(pq_file)
    
    if output:
        output_path = Path(output)
    else:
        output_path = pq_path.with_suffix('.pqout')
    
    try:
        runner = get_runner()
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    
    click.echo(f"Executing: {pq_path}")
    result = runner.execute_file(pq_path)
    
    if not result.success:
        click.echo(f"Execution failed: {result.error}", err=True)
        sys.exit(1)
    
    output_path.write_text(json.dumps(result.data, indent=2))
    click.echo(f"Snapshot saved: {output_path}")


if __name__ == "__main__":
    main()
