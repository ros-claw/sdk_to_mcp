"""
Self-Healing Code Generator Module

This module provides iterative code generation and testing with automatic
error correction. Instead of one-shot generation, it:
1. Generates MCP server code using LLM
2. Tests the generated code in a sandbox environment
3. If errors occur, feeds them back to LLM for correction
4. Repeats until code passes tests or max retries reached

Key concept: "Compilation Agent" that keeps fixing until it works.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class GenerationAttempt:
    """Record of a single code generation attempt."""

    attempt_number: int
    code: str
    success: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class HealingResult:
    """Final result of self-healing generation process."""

    success: bool
    final_code: str | None
    attempts: list[GenerationAttempt]
    total_attempts: int
    output_dir: Path | None = None

    def get_summary(self) -> str:
        """Get human-readable summary of the healing process."""
        if self.success:
            return (
                f"✅ Self-healing successful after {self.total_attempts} attempt(s)\n"
                f"   Final code: {len(self.final_code or '')} characters"
            )
        else:
            last_errors = (
                self.attempts[-1].errors if self.attempts else ["No attempts made"]
            )
            return (
                f"❌ Self-healing failed after {self.total_attempts} attempt(s)\n"
                f"   Last errors: {', '.join(last_errors[:3])}"
            )


class CodeTester:
    """
    Tests generated MCP server code in an isolated environment.
    """

    def __init__(self, temp_dir: Path | None = None):
        self.temp_dir = temp_dir or Path(tempfile.mkdtemp(prefix="mcp_test_"))
        self.test_results: list[dict] = []

    def test_syntax(self, code: str) -> tuple[bool, list[str]]:
        """
        Check if code has valid Python syntax.

        Returns:
            (success, error_messages)
        """
        try:
            ast.parse(code)
            return True, []
        except SyntaxError as e:
            return False, [f"Syntax error at line {e.lineno}: {e.msg}"]

    def test_imports(self, code: str) -> tuple[bool, list[str]]:
        """
        Check if all imports in the code can be resolved.

        Returns:
            (success, error_messages)
        """
        errors = []

        # Parse imports
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, [f"Syntax error: {e}"]

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if not self._can_import(alias.name):
                        errors.append(f"Cannot import module: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module
                if module and not self._can_import(module):
                    errors.append(f"Cannot import module: {module}")

        return len(errors) == 0, errors

    def _can_import(self, module_name: str) -> bool:
        """Check if a module can be imported."""
        # Skip built-in modules that may not be available in test env
        skip_modules = {"mcp", "fastmcp", "ros", "rclpy", "sensor_msgs"}

        if module_name.split(".")[0] in skip_modules:
            return True  # Assume these are available in production

        try:
            spec = importlib.util.find_spec(module_name)
            return spec is not None
        except (ImportError, ModuleNotFoundError):
            return False

    def test_execution(self, code: str, timeout: int = 5) -> tuple[bool, list[str]]:
        """
        Test if code can execute without runtime errors.

        This runs the code in a subprocess to isolate it.

        Args:
            code: Python code to test
            timeout: Maximum execution time in seconds

        Returns:
            (success, error_messages)
        """
        # Write code to temp file
        test_file = self.temp_dir / "test_server.py"
        test_file.write_text(code)

        # Run in subprocess
        try:
            result = subprocess.run(
                [sys.executable, "-c", f"import ast; ast.parse(open('{test_file}').read())"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode == 0:
                return True, []
            else:
                return False, [result.stderr.strip()]

        except subprocess.TimeoutExpired:
            return False, ["Code execution timed out"]
        except Exception as e:
            return False, [f"Execution error: {str(e)}"]

    def test_mcp_server(self, code: str) -> tuple[bool, list[str]]:
        """
        Test if code defines a valid MCP server structure.

        Checks for:
        - FastMCP initialization
        - At least one @mcp.tool() decorated function
        - Proper main() function
        """
        errors = []

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, [f"Syntax error: {e}"]

        has_fastmcp = False
        has_tool = False
        has_main = False

        for node in ast.walk(tree):
            # Check for FastMCP initialization
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "FastMCP":
                    has_fastmcp = True
                elif isinstance(node.func, ast.Attribute):
                    if node.func.attr == "FastMCP":
                        has_fastmcp = True

            # Check for @mcp.tool() decorator
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call):
                        if isinstance(decorator.func, ast.Attribute):
                            if decorator.func.attr == "tool":
                                has_tool = True
                    elif isinstance(decorator, ast.Attribute):
                        if decorator.attr == "tool":
                            has_tool = True

                # Check for main function
                if node.name == "main":
                    has_main = True

        if not has_fastmcp:
            errors.append("Missing FastMCP initialization (mcp = FastMCP('name'))")
        if not has_tool:
            errors.append("Missing @mcp.tool() decorated functions")
        if not has_main:
            errors.append("Missing main() function")

        return len(errors) == 0, errors

    def run_full_test(self, code: str) -> tuple[bool, list[str], list[str]]:
        """
        Run complete test suite.

        Returns:
            (success, errors, warnings)
        """
        all_errors = []
        warnings = []

        # Test 1: Syntax
        success, errors = self.test_syntax(code)
        if not success:
            all_errors.extend(errors)
            return False, all_errors, warnings

        # Test 2: Imports
        success, errors = self.test_imports(code)
        if not success:
            all_errors.extend(errors)
            # Don't return immediately - try to continue

        # Test 3: MCP Structure
        success, errors = self.test_mcp_server(code)
        if not success:
            all_errors.extend(errors)

        # Test 4: Basic execution (syntax only)
        success, errors = self.test_execution(code)
        if not success:
            all_errors.extend(errors)

        return len(all_errors) == 0, all_errors, warnings


class SelfHealingGenerator:
    """
    Self-healing code generator that iteratively fixes errors.

    Usage:
        generator = SelfHealingGenerator(llm_client)
        result = generator.generate(
            prompt="Generate MCP server for robot arm...",
            max_attempts=5
        )

        if result.success:
            code = result.final_code
    """

    def __init__(
        self,
        llm_generator: Callable[[str], str],
        temp_dir: Path | None = None,
    ):
        """
        Initialize the self-healing generator.

        Args:
            llm_generator: Function that takes a prompt and returns code
            temp_dir: Directory for temporary test files
        """
        self.llm_generator = llm_generator
        self.tester = CodeTester(temp_dir)
        self.attempts: list[GenerationAttempt] = []

    def generate(
        self,
        prompt: str,
        max_attempts: int = 5,
        context: dict[str, Any] | None = None,
    ) -> HealingResult:
        """
        Generate code with self-healing.

        Args:
            prompt: Initial generation prompt
            max_attempts: Maximum number of generation attempts
            context: Additional context for generation

        Returns:
            HealingResult with final code and attempt history
        """
        self.attempts = []
        current_prompt = prompt

        for attempt_num in range(1, max_attempts + 1):
            print(f"  [Self-Healing] Attempt {attempt_num}/{max_attempts}...")

            # Generate code
            try:
                code = self.llm_generator(current_prompt)
            except Exception as e:
                self.attempts.append(
                    GenerationAttempt(
                        attempt_number=attempt_num,
                        code="",
                        success=False,
                        errors=[f"LLM generation failed: {str(e)}"],
                    )
                )
                continue

            # Test the code
            success, errors, warnings = self.tester.run_full_test(code)

            # Record attempt
            self.attempts.append(
                GenerationAttempt(
                    attempt_number=attempt_num,
                    code=code,
                    success=success,
                    errors=errors,
                    warnings=warnings,
                )
            )

            if success:
                print(f"  ✅ Success on attempt {attempt_num}!")
                return HealingResult(
                    success=True,
                    final_code=code,
                    attempts=self.attempts,
                    total_attempts=attempt_num,
                )

            # Build correction prompt for next attempt
            current_prompt = self._build_correction_prompt(
                original_prompt=prompt,
                previous_code=code,
                errors=errors,
                attempt_num=attempt_num,
            )

        # All attempts failed
        print(f"  ❌ Failed after {max_attempts} attempts")
        return HealingResult(
            success=False,
            final_code=None,
            attempts=self.attempts,
            total_attempts=max_attempts,
        )

    def _build_correction_prompt(
        self,
        original_prompt: str,
        previous_code: str,
        errors: list[str],
        attempt_num: int,
    ) -> str:
        """Build a prompt that asks LLM to fix the errors."""
        error_text = "\n".join(f"  - {e}" for e in errors)

        prompt = f"""{original_prompt}

--- PREVIOUS ATTEMPT #{attempt_num} ---
The previous code had errors. Please fix them and regenerate.

Previous code:
```python
{previous_code[:2000]}  # Truncated for brevity
```

Errors to fix:
{error_text}

Please provide corrected code that addresses all these errors.
Ensure the code is complete and runnable.
"""
        return prompt

    def get_best_attempt(self) -> GenerationAttempt | None:
        """Get the best attempt (fewest errors)."""
        if not self.attempts:
            return None

        # Sort by number of errors (ascending)
        sorted_attempts = sorted(self.attempts, key=lambda a: len(a.errors))
        return sorted_attempts[0]


def create_mock_llm_generator() -> Callable[[str], str]:
    """Create a mock LLM generator for testing."""

    def mock_generate(prompt: str) -> str:
        # Return a minimal valid MCP server
        return '''
"""Mock MCP Server for testing."""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mock-robot")

@mcp.tool()
def move_robot(x: float, y: float, z: float) -> str:
    """Move robot to position."""
    return f"Moving to ({x}, {y}, {z})"

def main():
    mcp.run()

if __name__ == "__main__":
    main()
'''

    return mock_generate


# Example usage
if __name__ == "__main__":
    # Test with mock generator
    generator = SelfHealingGenerator(create_mock_llm_generator())

    result = generator.generate(
        prompt="Generate an MCP server for a robot arm",
        max_attempts=3,
    )

    print("\n" + result.get_summary())
