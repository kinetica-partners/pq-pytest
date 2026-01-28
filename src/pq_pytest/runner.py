"""
Power Query M Language Runtime Wrapper

This module provides a Python interface to execute Power Query M code
outside of Excel or Power BI, using either PowerQueryNet or PQTest.exe.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MExecutionResult:
    """Result of executing M code."""
    
    success: bool
    data: list[dict[str, Any]] | None = None
    error: str | None = None
    error_line: int | None = None
    error_column: int | None = None
    raw_output: str = ""
    execution_time_ms: float | None = None
    
    def to_dataframe(self):
        """Convert result data to a pandas DataFrame."""
        import pandas as pd
        
        if not self.success or self.data is None:
            raise ValueError(f"Cannot convert failed result to DataFrame: {self.error}")
        return pd.DataFrame(self.data)


@dataclass
class MExecutionContext:
    """Context for M code execution, including input data and parameters."""
    
    input_files: dict[str, Path] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 60
    working_dir: Path | None = None


class MRunner(ABC):
    """Abstract base class for M language runtime implementations."""
    
    @abstractmethod
    
    def is_available(self) -> bool:
        """Check if this runner is available on the system."""
        pass
    
    @abstractmethod
    def execute(
        self, 
        m_code: str, 
        context: MExecutionContext | None = None
    ) -> MExecutionResult:
        """Execute M code and return the result."""
        pass
    
    @abstractmethod
    def execute_file(
        self, 
        pq_file: Path, 
        context: MExecutionContext | None = None
    ) -> MExecutionResult:
        """Execute M code from a .pq file."""
        pass
    
    def _prepare_m_code(self, m_code: str, context: MExecutionContext) -> str:
        """Prepare M code by substituting parameters and input file paths."""
        result = m_code
        
        # Substitute input file paths
        for name, path in context.input_files.items():
            # Support both #"InputPath" style and InputPath style
            result = result.replace(f'#"{name}"', f'"{path}"')
            result = result.replace(f'#{name}', f'"{path}"')
            # Also support as a plain identifier (less safe but convenient)
            result = result.replace(f'[[{name}]]', f'"{path}"')
        
        # Substitute parameters
        for name, value in context.parameters.items():
            if isinstance(value, str):
                result = result.replace(f'#"{name}"', f'"{value}"')
                result = result.replace(f'[[{name}]]', f'"{value}"')
            elif isinstance(value, bool):
                m_bool = "true" if value else "false"
                result = result.replace(f'#"{name}"', m_bool)
                result = result.replace(f'[[{name}]]', m_bool)
            elif isinstance(value, (int, float)):
                result = result.replace(f'#"{name}"', str(value))
                result = result.replace(f'[[{name}]]', str(value))
        
        return result


class PowerQueryNetRunner(MRunner):
    """
    Runner implementation using PowerQueryNet (pqnet CLI).
    
    PowerQueryNet is a community tool that can execute M queries directly
    without requiring a custom connector.
    
    Install: https://github.com/gsimardnet/PowerQueryNet
    """
    
    def __init__(self, pqnet_path: str | None = None):
        self.pqnet_path = pqnet_path or "pqnet"
    
    def is_available(self) -> bool:
        """Check if pqnet is available."""
        try:
            result = subprocess.run(
                [self.pqnet_path], 
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def execute(
        self, 
        m_code: str, 
        context: MExecutionContext | None = None
    ) -> MExecutionResult:
        """Execute M code string."""
        context = context or MExecutionContext()
        
        # Create temp file for the M code
        with tempfile.NamedTemporaryFile(
            mode='w', 
            suffix='.pq', 
            delete=False,
            dir=context.working_dir
        ) as f:
            prepared_code = self._prepare_m_code(m_code, context)
            f.write(prepared_code)
            temp_path = Path(f.name)
        
        try:
            return self.execute_file(temp_path, context)
        finally:
            temp_path.unlink(missing_ok=True)
    
    def execute_file(
        self, 
        pq_file: Path, 
        context: MExecutionContext | None = None
    ) -> MExecutionResult:
        """Execute M code from a .pq file."""
        context = context or MExecutionContext()
        
        # If we have input files, we need to prepare the code
        if context.input_files or context.parameters:
            m_code = pq_file.read_text(encoding='utf-8')
            return self.execute(m_code, context)
        
        cmd = [self.pqnet_path, str(pq_file), "-o", "json"]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=context.timeout_seconds,
                cwd=context.working_dir
            )
            
            if result.returncode != 0:
                return self._parse_error(result.stderr, result.stdout)
            
            return self._parse_success(result.stdout)
            
        except subprocess.TimeoutExpired:
            return MExecutionResult(
                success=False,
                error=f"Execution timed out after {context.timeout_seconds} seconds"
            )
        except Exception as e:
            return MExecutionResult(
                success=False,
                error=f"Execution failed: {str(e)}"
            )
    
    def _parse_success(self, stdout: str) -> MExecutionResult:
        """Parse successful execution output."""
        try:
            data = json.loads(stdout)
            # pqnet returns data in various formats, normalize to list of dicts
            if isinstance(data, dict):
                data = [data]
            return MExecutionResult(success=True, data=data, raw_output=stdout)
        except json.JSONDecodeError as e:
            return MExecutionResult(
                success=False,
                error=f"Failed to parse output as JSON: {e}",
                raw_output=stdout
            )
    
    def _parse_error(self, stderr: str, stdout: str) -> MExecutionResult:
        """Parse error output and extract line/column info if available."""
        error_line = None
        error_column = None
        
        # Try to extract position info from error message
        # Format: "Error at line X, column Y: message"
        import re
        match = re.search(r'line\s+(\d+)', stderr, re.IGNORECASE)
        if match:
            error_line = int(match.group(1))
        match = re.search(r'column\s+(\d+)', stderr, re.IGNORECASE)
        if match:
            error_column = int(match.group(1))
        
        return MExecutionResult(
            success=False,
            error=stderr or stdout,
            error_line=error_line,
            error_column=error_column,
            raw_output=stdout
        )


class PQTestRunner(MRunner):
    """
    Runner implementation using Microsoft's PQTest.exe from the Power Query SDK.
    
    This requires:
    1. A minimal .mez connector file (we provide a passthrough connector)
    2. The Power Query SDK installed via VS Code extension
    
    More robust than PowerQueryNet, actively maintained by Microsoft.
    """
    
    def __init__(
        self, 
        pqtest_path: str | None = None,
        connector_path: str | None = None
    ):
        self.pqtest_path = pqtest_path or self._find_pqtest()
        self.connector_path = connector_path
    
    def _find_pqtest(self) -> str | None:
        """Try to find PQTest.exe in common locations."""
        # Check VS Code extensions directory
        home = Path.home()
        vscode_ext = home / ".vscode" / "extensions"
        
        if vscode_ext.exists():
            # Look for powerquery SDK extension
            for ext_dir in vscode_ext.glob("powerquery.vscode-powerquery-sdk-*"):
                pqtest = ext_dir / ".nuget" / "Microsoft.PowerQuery.SdkTools.*" / "tools" / "PQTest.exe"
                # Glob for version
                for match in ext_dir.glob(".nuget/Microsoft.PowerQuery.SdkTools.*/tools/PQTest.exe"):
                    return str(match)
        
        # Check if it's in PATH
        pqtest = shutil.which("PQTest.exe") or shutil.which("pqtest")
        if pqtest:
            return pqtest
        
        return None
    
    def is_available(self) -> bool:
        """Check if PQTest is available."""
        if not self.pqtest_path:
            return False
        try:
            result = subprocess.run(
                [self.pqtest_path, "--help"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def execute(
        self, 
        m_code: str, 
        context: MExecutionContext | None = None
    ) -> MExecutionResult:
        """Execute M code string."""
        context = context or MExecutionContext()
        
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.query.pq',
            delete=False,
            dir=context.working_dir
        ) as f:
            prepared_code = self._prepare_m_code(m_code, context)
            f.write(prepared_code)
            temp_path = Path(f.name)
        
        try:
            return self.execute_file(temp_path, context)
        finally:
            temp_path.unlink(missing_ok=True)
    
    def execute_file(
        self, 
        pq_file: Path, 
        context: MExecutionContext | None = None
    ) -> MExecutionResult:
        """Execute M code from a .pq file."""
        context = context or MExecutionContext()
        
        if not self.connector_path:
            return MExecutionResult(
                success=False,
                error="PQTest requires a connector (.mez) file. "
                      "Use PowerQueryNetRunner or provide a connector path."
            )
        
        # If we have input files, we need to prepare the code
        if context.input_files or context.parameters:
            m_code = pq_file.read_text(encoding='utf-8')
            return self.execute(m_code, context)
        
        cmd = [
            self.pqtest_path,
            "run-test",
            "--extension", self.connector_path,
            "--queryFile", str(pq_file),
            "--prettyPrint"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=context.timeout_seconds,
                cwd=context.working_dir
            )
            
            return self._parse_pqtest_output(result.stdout, result.stderr, result.returncode)
            
        except subprocess.TimeoutExpired:
            return MExecutionResult(
                success=False,
                error=f"Execution timed out after {context.timeout_seconds} seconds"
            )
        except Exception as e:
            return MExecutionResult(
                success=False,
                error=f"Execution failed: {str(e)}"
            )
    
    def _parse_pqtest_output(
        self, 
        stdout: str, 
        stderr: str, 
        returncode: int
    ) -> MExecutionResult:
        """Parse PQTest JSON output format."""
        try:
            # PQTest returns a JSON array with test results
            results = json.loads(stdout)
            if isinstance(results, list) and len(results) > 0:
                test_result = results[0]
                
                if test_result.get("Status") == "Passed":
                    output = test_result.get("Output", [])
                    # Extract actual data from output
                    return MExecutionResult(
                        success=True,
                        data=output,
                        raw_output=stdout
                    )
                else:
                    return MExecutionResult(
                        success=False,
                        error=test_result.get("Details", "Unknown error"),
                        raw_output=stdout
                    )
            
            return MExecutionResult(
                success=False,
                error=f"Unexpected output format: {stdout}",
                raw_output=stdout
            )
            
        except json.JSONDecodeError:
            return MExecutionResult(
                success=False,
                error=stderr or stdout or "Unknown error",
                raw_output=stdout
            )


class MockRunner(MRunner):
    """
    Mock runner for testing the framework itself.
    
    Also useful for developing M code when no runtime is available -
    you can define expected outputs and test your Python test logic.
    """
    
    def __init__(self):
        self.responses: dict[str, MExecutionResult] = {}
        self.call_log: list[tuple[str, MExecutionContext | None]] = []
    
    def set_response(self, m_code_pattern: str, result: MExecutionResult):
        """Set the response for a given M code pattern."""
        self.responses[m_code_pattern] = result
    
    def is_available(self) -> bool:
        return True
    
    def execute(
        self, 
        m_code: str, 
        context: MExecutionContext | None = None
    ) -> MExecutionResult:
        self.call_log.append((m_code, context))
        
        # Check for matching pattern
        for pattern, result in self.responses.items():
            if pattern in m_code:
                return result
        
        # Default: return empty success
        return MExecutionResult(success=True, data=[])
    
    def execute_file(
        self, 
        pq_file: Path, 
        context: MExecutionContext | None = None
    ) -> MExecutionResult:
        m_code = pq_file.read_text(encoding='utf-8')
        return self.execute(m_code, context)


def get_runner(preferred: str | None = None) -> MRunner:
    """
    Get the best available M runner.
    
    Args:
        preferred: Preferred runner type ('pqnet', 'pqtest', 'mock')
    
    Returns:
        An MRunner instance
    
    Raises:
        RuntimeError: If no runner is available
    """
    runners: list[tuple[str, MRunner]] = [
        ('pqnet', PowerQueryNetRunner()),
        ('pqtest', PQTestRunner()),
    ]
    
    # If preferred, try that first
    if preferred:
        for name, runner in runners:
            if name == preferred and runner.is_available():
                return runner
    
    # Otherwise, find first available
    for name, runner in runners:
        if runner.is_available():
            return runner
    
    raise RuntimeError(
        "No Power Query runtime found. Please install one of:\n"
        "  - PowerQueryNet: https://github.com/gsimardnet/PowerQueryNet\n"
        "  - Power Query SDK: VS Code extension 'powerquery.vscode-powerquery-sdk'"
    )
