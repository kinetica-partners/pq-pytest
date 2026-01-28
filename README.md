# pq-pytest

Test Power Query M code with pytest - no Excel or Power BI required.

`pq-pytest` provides a Python testing framework for Power Query M language transforms, allowing you to write automated tests for your M code using pytest and run them against a standalone M runtime.

## Features

- **pytest integration**: Use familiar pytest fixtures and assertions
- **Auto-discovery**: Automatically finds PowerQueryNet installation
- **Auto-credentials**: Generates file access credentials automatically
- **Multiple runtimes**: Supports PowerQueryNet and PQTest.exe
- **DataFrame integration**: Convert results to pandas DataFrames
- **CLI tools**: Run M code, check setup, scaffold new transforms

## Prerequisites

### Install PowerQueryNet (Recommended)

PowerQueryNet is a free, open-source tool that executes Power Query M code outside of Excel/Power BI.

1. Download from [PowerQueryNet Releases](https://github.com/gsimardnet/PowerQueryNet/releases)
2. Run the installer (installs to `C:\Program Files\PowerQueryNet\` by default)
3. **That's it!** No PATH configuration needed - pq-pytest auto-detects the installation

### Alternative: Power Query SDK (Advanced)

The Power Query SDK requires additional setup (connector file) and is primarily for connector development. For most testing scenarios, PowerQueryNet is simpler.

## Installation

This package is installed directly from GitHub (not PyPI).

### Using pip

```bash
pip install git+https://github.com/YOUR_USERNAME/pq-pytest.git
```

### Using uv

```bash
uv add git+https://github.com/YOUR_USERNAME/pq-pytest.git
```

### In pyproject.toml

```toml
[project]
dependencies = [
    "pq-pytest @ git+https://github.com/YOUR_USERNAME/pq-pytest.git",
]
```

### Install a specific version/branch

```bash
# Specific tag
pip install git+https://github.com/YOUR_USERNAME/pq-pytest.git@v0.1.0

# Specific branch
pip install git+https://github.com/YOUR_USERNAME/pq-pytest.git@main

# Specific commit
pip install git+https://github.com/YOUR_USERNAME/pq-pytest.git@abc1234
```

## Quick Start

### 1. Create an M Transform

Create `transforms/clean_data.pq`:

```powerquery
// Input: [[InputPath]] - CSV file path
// Output: Cleaned table

let
    Source = Csv.Document(
        File.Contents([[InputPath]]),
        [Delimiter=",", Encoding=65001]
    ),
    PromotedHeaders = Table.PromoteHeaders(Source),

    // Remove rows with null values
    Cleaned = Table.SelectRows(PromotedHeaders, each [Name] <> null)
in
    Cleaned
```

### 2. Write a Test

Create `tests/test_clean_data.py`:

```python
from pathlib import Path

TRANSFORMS = Path(__file__).parent.parent / "transforms"


class TestCleanData:
    def test_removes_null_rows(self, pq_execute_file, pq_assert, tmp_path):
        # Create test input
        input_file = tmp_path / "input.csv"
        input_file.write_text("Name,Value\nAlice,100\n,200\nBob,300\n")

        # Execute the transform
        result = pq_execute_file(
            TRANSFORMS / "clean_data.pq",
            input_files={"InputPath": input_file}
        )

        # Assert results
        pq_assert.assert_success(result)
        pq_assert.assert_row_count(result, 2)  # Null row removed

    def test_has_expected_columns(self, pq_execute_file, pq_assert, tmp_path):
        input_file = tmp_path / "input.csv"
        input_file.write_text("Name,Value\nAlice,100\n")

        result = pq_execute_file(
            TRANSFORMS / "clean_data.pq",
            input_files={"InputPath": input_file}
        )

        pq_assert.assert_success(result)
        pq_assert.assert_columns(result, ["Name", "Value"])
```

### 3. Run Tests

```bash
pytest tests/
```

## Fixtures Reference

### `pq_execute_file`

Execute an M transform file with input files and parameters:

```python
def test_example(pq_execute_file, pq_assert, tmp_path):
    input_file = tmp_path / "data.csv"
    input_file.write_text("col1,col2\n1,2\n")

    result = pq_execute_file(
        "transforms/my_transform.pq",
        input_files={"InputPath": input_file},
        parameters={"MaxRows": 100}
    )

    pq_assert.assert_success(result)
```

### `pq_execute`

Execute inline M code:

```python
def test_inline(pq_execute, pq_assert):
    result = pq_execute('let x = 1 + 1 in x')
    pq_assert.assert_success(result)
```

### `pq_assert`

Assertion helpers for M execution results:

```python
pq_assert.assert_success(result)           # Assert execution succeeded
pq_assert.assert_row_count(result, 10)     # Assert row count
pq_assert.assert_columns(result, ["a","b"]) # Assert column names
pq_assert.assert_dataframe_equal(result, expected_df)  # Compare to DataFrame
```

### `pq_runner`

Direct access to the M runtime (session-scoped):

```python
def test_direct(pq_runner):
    result = pq_runner.execute('let x = 1 in x')
    assert result.success
    assert result.data == [{"Value": 1}]
```

## Input Placeholders

In your M code, use `[[Name]]` syntax for inputs that will be substituted at test time:

```powerquery
let
    // File path - will be replaced with actual path
    Source = File.Contents([[InputPath]]),

    // Parameter - will be replaced with value
    Filtered = Table.FirstN(Data, [[MaxRows]])
in
    Filtered
```

Then in tests:

```python
result = pq_execute_file(
    "transform.pq",
    input_files={"InputPath": tmp_path / "data.csv"},
    parameters={"MaxRows": 100}
)
```

## CLI Usage

### Check Runtime Availability

```bash
pq check
```

Output:
```
Checking Power Query runtimes...

✓ PowerQueryNet (pqnet): Available
  Path: C:\Program Files\PowerQueryNet\PQNet.exe

✗ PQTest.exe: Not found
  Install Power Query SDK VS Code extension

Default runner: PowerQueryNetRunner
```

### Run M Code

```bash
# Run from file
pq run transforms/my_transform.pq

# Run with inputs
pq run transform.pq -i InputPath data/input.csv

# Run with parameters
pq run transform.pq -p MaxRows 100

# Run inline code
pq run -c "let x = 1 + 1 in x"

# Output formats
pq run transform.pq -o json    # JSON (default)
pq run transform.pq -o csv     # CSV
pq run transform.pq -o table   # ASCII table
```

### Scaffold New Transform

```bash
pq scaffold my_new_transform
```

Creates:
- `transforms/my_new_transform.pq` - M code template
- `tests/test_my_new_transform.py` - Python test file
- `tests/fixtures/my_new_transform_input.csv` - Sample input
- `tests/fixtures/my_new_transform_expected.csv` - Expected output

## Configuration

### pytest Options

```bash
# Use specific runner
pytest --pq-runner=pqnet
pytest --pq-runner=mock    # For testing without runtime

# Set timeout
pytest --pq-timeout=120
```

### Custom Runner Configuration

If PowerQueryNet is installed in a non-standard location:

```python
# conftest.py
import pytest
from pq_pytest.runner import PowerQueryNetRunner

@pytest.fixture(scope="session")
def pq_runner():
    return PowerQueryNetRunner(
        pqnet_path=r"D:\Tools\PowerQueryNet\PQNet.exe",
        credentials_path=r"D:\my_credentials.xml"  # Optional
    )
```

## Working with Results

### Convert to DataFrame

```python
def test_dataframe(pq_execute_file, pq_assert, tmp_path):
    # ... execute transform ...

    pq_assert.assert_success(result)
    df = result.to_dataframe()

    # Now use pandas operations
    assert df["Amount"].sum() == 1000
    assert len(df[df["Status"] == "Active"]) == 5
```

### Access Raw Data

```python
result = pq_execute_file(...)
if result.success:
    for row in result.data:
        print(row)  # Each row is a dict
```

## Troubleshooting

### "No Power Query runtime found"

Install PowerQueryNet:
1. Download from https://github.com/gsimardnet/PowerQueryNet/releases
2. Run the installer
3. Run `pq check` to verify

### "Credentials are required to connect to the File source"

This should be handled automatically. If you see this error:
- Ensure you're passing input files via `input_files={"InputPath": path}`
- The path must be a `Path` object or string pointing to an existing file

### Tests pass individually but fail together

Each test should use `tmp_path` fixture for isolation:

```python
def test_example(pq_execute_file, tmp_path):  # Use tmp_path!
    input_file = tmp_path / "input.csv"
    # ...
```

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions welcome! Please open an issue or PR on GitHub.
