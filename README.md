# pq-pytest

**Test Power Query M code with pytest — no Excel required.**

Write your data transforms in Power Query M, test them with Python and pytest, and iterate rapidly with AI assistance (Claude Code, Copilot, etc.).

## The Problem

Power Query M is powerful for data transformation, but developing M code is painful:

- The "Advanced Editor" in Excel/Power BI is basically Notepad
- No real testing framework
- Can't run M code outside of a spreadsheet
- Copy-pasting between Claude/Copilot and Excel is tedious
- No CI/CD pipeline possible

## The Solution

`pq-pytest` gives you:

- ✅ Run M code from the command line
- ✅ Write tests in Python with pytest
- ✅ Use fixtures, assertions, and all pytest features
- ✅ Integrate with Claude Code for AI-assisted development
- ✅ CI/CD ready

## Installation

```bash
pip install pq-pytest
```

You also need an M runtime. Choose one:

### Option A: PowerQueryNet (Recommended for simplicity)

Download from [PowerQueryNet releases](https://github.com/gsimardnet/PowerQueryNet/releases) and install. The `pqnet` command should be available in your PATH.

### Option B: Power Query SDK (Official Microsoft)

1. Install [VS Code](https://code.visualstudio.com/)
2. Install the [Power Query SDK extension](https://marketplace.visualstudio.com/items?itemName=PowerQuery.vscode-powerquery-sdk)

The SDK installs `PQTest.exe` which pq-pytest can use.

## Quick Start

### 1. Check your setup

```bash
pq check
```

Output:
```
Checking Power Query runtimes...

✓ PowerQueryNet (pqnet): Available
  Path: C:\Program Files\PowerQueryNet\pqnet.exe

Default runner: PowerQueryNetRunner
```

### 2. Create a test scaffold

```bash
pq scaffold clean_inventory
```

This creates:
```
transforms/
  clean_inventory.pq      # Your M code
tests/
  test_clean_inventory.py # Python tests
  fixtures/
    clean_inventory_input.csv
    clean_inventory_expected.csv
```

### 3. Write your M transform

Edit `transforms/clean_inventory.pq`:

```m
let
    // Load input data
    Source = Csv.Document(
        File.Contents([[InputPath]]),
        [Delimiter=",", Encoding=65001]
    ),
    
    // Promote headers
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    
    // Type the columns
    Typed = Table.TransformColumnTypes(Headers, {
        {"SKU", type text},
        {"Quantity", Int64.Type},
        {"LastUpdated", type date}
    }),
    
    // Filter out negative quantities
    Filtered = Table.SelectRows(Typed, each [Quantity] >= 0),
    
    // Add a computed column
    WithStatus = Table.AddColumn(Filtered, "Status", each 
        if [Quantity] = 0 then "Out of Stock"
        else if [Quantity] < 10 then "Low Stock"
        else "In Stock"
    )
in
    WithStatus
```

Note the `[[InputPath]]` placeholder — this gets replaced with the actual file path at runtime.

### 4. Write your tests

Edit `tests/test_clean_inventory.py`:

```python
from pathlib import Path
import pandas as pd
import pytest

TRANSFORMS_DIR = Path(__file__).parent.parent / "transforms"

class TestCleanInventory:
    
    def test_filters_negative_quantities(self, pq_execute_file, pq_assert, tmp_path):
        # Create input with negative quantity
        input_file = tmp_path / "input.csv"
        input_file.write_text(
            "SKU,Quantity,LastUpdated\n"
            "ABC,10,2024-01-01\n"
            "DEF,-5,2024-01-01\n"  # Should be filtered
            "GHI,0,2024-01-01\n"
        )
        
        result = pq_execute_file(
            TRANSFORMS_DIR / "clean_inventory.pq",
            input_files={"InputPath": input_file}
        )
        
        pq_assert.assert_success(result)
        pq_assert.assert_row_count(result, 2)  # DEF should be filtered out
    
    def test_adds_status_column(self, pq_execute_file, pq_assert, tmp_path):
        input_file = tmp_path / "input.csv"
        input_file.write_text(
            "SKU,Quantity,LastUpdated\n"
            "ABC,0,2024-01-01\n"
            "DEF,5,2024-01-01\n"
            "GHI,100,2024-01-01\n"
        )
        
        result = pq_execute_file(
            TRANSFORMS_DIR / "clean_inventory.pq",
            input_files={"InputPath": input_file}
        )
        
        pq_assert.assert_success(result)
        df = result.to_dataframe()
        
        assert df.loc[df["SKU"] == "ABC", "Status"].iloc[0] == "Out of Stock"
        assert df.loc[df["SKU"] == "DEF", "Status"].iloc[0] == "Low Stock"
        assert df.loc[df["SKU"] == "GHI", "Status"].iloc[0] == "In Stock"
    
    def test_matches_expected_output(self, pq_execute_file, pq_assert, tmp_path):
        # Use fixture files
        input_file = tmp_path / "input.csv"
        input_file.write_text(Path("tests/fixtures/clean_inventory_input.csv").read_text())
        
        expected = pd.read_csv("tests/fixtures/clean_inventory_expected.csv")
        
        result = pq_execute_file(
            TRANSFORMS_DIR / "clean_inventory.pq",
            input_files={"InputPath": input_file}
        )
        
        pq_assert.assert_success(result)
        pq_assert.assert_dataframe_equal(result, expected)
```

### 5. Run tests

```bash
pytest tests/ -v
```

Output:
```
tests/test_clean_inventory.py::TestCleanInventory::test_filters_negative_quantities PASSED
tests/test_clean_inventory.py::TestCleanInventory::test_adds_status_column PASSED
tests/test_clean_inventory.py::TestCleanInventory::test_matches_expected_output PASSED
```

## CLI Reference

### `pq run` - Execute M code

```bash
# Run from file
pq run transforms/my_transform.pq

# Run with input files
pq run transforms/my_transform.pq -i InputPath data/input.csv

# Run with parameters
pq run transforms/my_transform.pq -p Threshold 100

# Run inline code
pq run -c "let x = 1 + 1 in x"

# Output formats
pq run transform.pq -o json   # JSON (default)
pq run transform.pq -o csv    # CSV
pq run transform.pq -o table  # Formatted table
```

### `pq check` - Check runtime availability

```bash
pq check
```

### `pq scaffold` - Create test scaffold

```bash
pq scaffold my_transform
```

### `pq snapshot` - Generate expected output

```bash
pq snapshot transforms/my_transform.pq
# Creates transforms/my_transform.pqout
```

## Fixtures Reference

### `pq_runner`

The M runtime instance. Usually you'll use the higher-level fixtures instead.

```python
def test_low_level(pq_runner):
    result = pq_runner.execute("let x = 1 in x")
    assert result.success
```

### `pq_context`

Execution context with input files, parameters, and settings.

```python
def test_with_context(pq_runner, pq_context, tmp_path):
    pq_context.input_files["MyInput"] = tmp_path / "data.csv"
    pq_context.parameters["Threshold"] = 100
    pq_context.timeout_seconds = 120
    
    result = pq_runner.execute(m_code, pq_context)
```

### `pq_execute`

Convenience fixture combining runner and context.

```python
def test_simple(pq_execute):
    result = pq_execute("let x = 1 + 1 in x")
    assert result.success
```

### `pq_execute_file`

Execute M code from a file.

```python
def test_from_file(pq_execute_file):
    result = pq_execute_file(
        "transforms/my_transform.pq",
        input_files={"InputPath": some_file}
    )
    assert result.success
```

### `pq_assert`

Assertion helpers.

```python
def test_with_assertions(pq_execute, pq_assert):
    result = pq_execute(m_code)
    
    pq_assert.assert_success(result)
    pq_assert.assert_row_count(result, 10)
    pq_assert.assert_columns(result, ["id", "name", "value"])
    pq_assert.assert_dataframe_equal(result, expected_df)
    pq_assert.assert_output_matches_file(result, "expected.csv")
```

### `pq_mock_runner`

Mock runner for testing without a real runtime.

```python
def test_with_mock(pq_mock_runner):
    pq_mock_runner.set_response(
        "MyQuery",
        MExecutionResult(success=True, data=[{"col": 1}])
    )
    
    result = pq_mock_runner.execute("let x = MyQuery() in x")
    assert result.data == [{"col": 1}]
```

## Integration with Claude Code

This package is designed to work seamlessly with AI coding assistants. The workflow:

1. **You describe what you want**: "Create an M transform that cleans inventory data by removing negative quantities and adding a stock status column"

2. **Claude writes the M code** and saves it to `transforms/clean_inventory.pq`

3. **Claude writes tests** in `tests/test_clean_inventory.py`

4. **Claude runs the tests**: `pytest tests/test_clean_inventory.py -v`

5. **If tests fail**, Claude sees the error output and iterates

The CLI's JSON output format is designed for easy parsing:

```bash
pq run transform.pq -o json
```

```json
{
  "success": true,
  "data": [
    {"SKU": "ABC", "Quantity": 10, "Status": "In Stock"},
    {"SKU": "DEF", "Quantity": 0, "Status": "Out of Stock"}
  ]
}
```

Or on error:

```json
{
  "success": false,
  "error": "Expression.Error: The column 'Price' of the table wasn't found.",
  "line": 15,
  "column": 8
}
```

## Input Placeholder Syntax

Use these patterns in your M code to mark where input file paths should be injected:

| Pattern | Example | Description |
|---------|---------|-------------|
| `[[Name]]` | `File.Contents([[InputPath]])` | Recommended - clear and explicit |
| `#"Name"` | `File.Contents(#"InputPath")` | M-style identifier (can conflict with step names) |

The placeholder is replaced with the actual file path at runtime.

## Project Structure

Recommended project structure:

```
my-project/
├── transforms/           # M code files
│   ├── clean_inventory.pq
│   ├── calculate_reorder.pq
│   └── aggregate_sales.pq
├── tests/
│   ├── conftest.py       # Shared fixtures
│   ├── fixtures/         # Test data
│   │   ├── inventory_input.csv
│   │   └── inventory_expected.csv
│   ├── test_clean_inventory.py
│   └── test_calculate_reorder.py
├── pyproject.toml
└── README.md
```

## Limitations

- **Output limited to 1000 rows** with PQTest.exe (SDK limitation)
- **No DirectQuery support** - only import mode
- **Windows only** for PowerQueryNet; PQTest requires Windows too
- **Some M functions may not work** outside Power BI (e.g., `PowerBI.Dataflows`)

## Contributing

Contributions welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT License - see [LICENSE](LICENSE).

## Acknowledgments

- [PowerQueryNet](https://github.com/gsimardnet/PowerQueryNet) by Gabriel Simard
- [Power Query SDK](https://github.com/microsoft/vscode-powerquery-sdk) by Microsoft
- The Power Query team at Microsoft
