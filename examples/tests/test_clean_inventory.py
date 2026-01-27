"""
Tests for clean_inventory transform.

This demonstrates how to test Power Query M code using pq-pytest.
"""

from pathlib import Path

import pandas as pd
import pytest

# Paths relative to this file
FIXTURES_DIR = Path(__file__).parent / "fixtures"
TRANSFORMS_DIR = Path(__file__).parent.parent / "transforms"


class TestCleanInventory:
    """Tests for the clean_inventory transform."""

    @pytest.fixture
    def standard_input(self, tmp_path) -> Path:
        """Create standard test input from fixture."""
        fixture_content = (FIXTURES_DIR / "clean_inventory_input.csv").read_text()
        input_file = tmp_path / "input.csv"
        input_file.write_text(fixture_content)
        return input_file

    @pytest.fixture
    def expected_output(self) -> pd.DataFrame:
        """Load expected output from fixture."""
        return pd.read_csv(FIXTURES_DIR / "clean_inventory_expected.csv")

    # -------------------------------------------------------------------------
    # Basic Success Tests
    # -------------------------------------------------------------------------

    def test_transform_succeeds_with_valid_input(
        self, pq_execute_file, pq_assert, standard_input
    ):
        """Transform should execute successfully with valid input."""
        result = pq_execute_file(
            TRANSFORMS_DIR / "clean_inventory.pq",
            input_files={"InputPath": standard_input}
        )

        pq_assert.assert_success(result)

    def test_produces_expected_columns(
        self, pq_execute_file, pq_assert, standard_input
    ):
        """Transform should produce expected output columns."""
        result = pq_execute_file(
            TRANSFORMS_DIR / "clean_inventory.pq",
            input_files={"InputPath": standard_input}
        )

        pq_assert.assert_success(result)
        pq_assert.assert_columns(result, ["SKU", "Quantity", "LastUpdated", "Status"])

    def test_matches_expected_output(
        self, pq_execute_file, pq_assert, standard_input, expected_output
    ):
        """Transform output should match expected fixture."""
        result = pq_execute_file(
            TRANSFORMS_DIR / "clean_inventory.pq",
            input_files={"InputPath": standard_input}
        )

        pq_assert.assert_success(result)
        # Note: We might need to handle date type differences
        pq_assert.assert_dataframe_equal(result, expected_output, check_dtype=False)

    # -------------------------------------------------------------------------
    # Business Logic Tests
    # -------------------------------------------------------------------------

    def test_filters_negative_quantities(self, pq_execute_file, pq_assert, tmp_path):
        """Rows with negative quantities should be filtered out."""
        input_file = tmp_path / "input.csv"
        input_file.write_text(
            "SKU,Quantity,LastUpdated\n"
            "VALID,10,2024-01-01\n"
            "NEGATIVE,-5,2024-01-01\n"
            "ZERO,0,2024-01-01\n"
        )

        result = pq_execute_file(
            TRANSFORMS_DIR / "clean_inventory.pq",
            input_files={"InputPath": input_file}
        )

        pq_assert.assert_success(result)
        pq_assert.assert_row_count(result, 2)  # NEGATIVE should be filtered

        df = result.to_dataframe()
        assert "NEGATIVE" not in df["SKU"].values
        assert "VALID" in df["SKU"].values
        assert "ZERO" in df["SKU"].values

    def test_status_out_of_stock(self, pq_execute_file, pq_assert, tmp_path):
        """Quantity of 0 should result in 'Out of Stock' status."""
        input_file = tmp_path / "input.csv"
        input_file.write_text("SKU,Quantity,LastUpdated\nTEST,0,2024-01-01\n")

        result = pq_execute_file(
            TRANSFORMS_DIR / "clean_inventory.pq",
            input_files={"InputPath": input_file}
        )

        pq_assert.assert_success(result)
        df = result.to_dataframe()
        assert df.iloc[0]["Status"] == "Out of Stock"

    def test_status_low_stock(self, pq_execute_file, pq_assert, tmp_path):
        """Quantity 1-9 should result in 'Low Stock' status."""
        input_file = tmp_path / "input.csv"
        input_file.write_text(
            "SKU,Quantity,LastUpdated\n"
            "LOW1,1,2024-01-01\n"
            "LOW5,5,2024-01-01\n"
            "LOW9,9,2024-01-01\n"
        )

        result = pq_execute_file(
            TRANSFORMS_DIR / "clean_inventory.pq",
            input_files={"InputPath": input_file}
        )

        pq_assert.assert_success(result)
        df = result.to_dataframe()
        assert (df["Status"] == "Low Stock").all()

    def test_status_in_stock(self, pq_execute_file, pq_assert, tmp_path):
        """Quantity >= 10 should result in 'In Stock' status."""
        input_file = tmp_path / "input.csv"
        input_file.write_text(
            "SKU,Quantity,LastUpdated\n"
            "STOCK10,10,2024-01-01\n"
            "STOCK100,100,2024-01-01\n"
        )

        result = pq_execute_file(
            TRANSFORMS_DIR / "clean_inventory.pq",
            input_files={"InputPath": input_file}
        )

        pq_assert.assert_success(result)
        df = result.to_dataframe()
        assert (df["Status"] == "In Stock").all()

    # -------------------------------------------------------------------------
    # Edge Case Tests
    # -------------------------------------------------------------------------

    def test_handles_empty_input(self, pq_execute_file, pq_assert, tmp_path):
        """Transform should handle empty input (headers only)."""
        input_file = tmp_path / "empty.csv"
        input_file.write_text("SKU,Quantity,LastUpdated\n")

        result = pq_execute_file(
            TRANSFORMS_DIR / "clean_inventory.pq",
            input_files={"InputPath": input_file}
        )

        pq_assert.assert_success(result)
        pq_assert.assert_row_count(result, 0)

    def test_handles_single_row(self, pq_execute_file, pq_assert, tmp_path):
        """Transform should handle single row input."""
        input_file = tmp_path / "single.csv"
        input_file.write_text("SKU,Quantity,LastUpdated\nONLY,42,2024-01-01\n")

        result = pq_execute_file(
            TRANSFORMS_DIR / "clean_inventory.pq",
            input_files={"InputPath": input_file}
        )

        pq_assert.assert_success(result)
        pq_assert.assert_row_count(result, 1)

    def test_preserves_sku_with_special_characters(
        self, pq_execute_file, pq_assert, tmp_path
    ):
        """SKUs with dashes and numbers should be preserved."""
        input_file = tmp_path / "special.csv"
        input_file.write_text(
            "SKU,Quantity,LastUpdated\n"
            "ABC-123-XYZ,50,2024-01-01\n"
            "999-000,25,2024-01-01\n"
        )

        result = pq_execute_file(
            TRANSFORMS_DIR / "clean_inventory.pq",
            input_files={"InputPath": input_file}
        )

        pq_assert.assert_success(result)
        df = result.to_dataframe()
        assert "ABC-123-XYZ" in df["SKU"].values
        assert "999-000" in df["SKU"].values


class TestCleanInventoryWithMock:
    """
    Demonstrate testing with mock runner.
    
    Useful when you don't have the M runtime installed,
    or for testing the test infrastructure itself.
    """

    def test_mock_runner_example(self, pq_mock_runner):
        """Show how to use the mock runner."""
        from pq_pytest import MExecutionResult

        # Set up mock response
        pq_mock_runner.set_response(
            "clean_inventory",
            MExecutionResult(
                success=True,
                data=[
                    {"SKU": "TEST-001", "Quantity": 50, "Status": "In Stock"},
                    {"SKU": "TEST-002", "Quantity": 0, "Status": "Out of Stock"},
                ]
            )
        )

        # Execute (the mock will return our predefined response)
        result = pq_mock_runner.execute("let x = clean_inventory() in x")

        assert result.success
        assert len(result.data) == 2
        assert result.data[0]["SKU"] == "TEST-001"
