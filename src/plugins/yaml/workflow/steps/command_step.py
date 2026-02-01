"""
Command Step

Executes shell commands with restricted allowlist.
"""

import subprocess
import shlex
from typing import Any, Optional

from ..context import WorkflowContext
from .base import BaseStep, StepResult, StepError
from ...encoding.encoder import TemplateProcessor


# Whitelist of allowed commands
ALLOWED_COMMANDS = {
    "gp": "GlobalPlatformPro",
    "gp.exe": "GlobalPlatformPro (Windows)",
    "openssl": "OpenSSL",
    "gpg": "GnuPG",
    "java": "Java (for GP)",
    "echo": "Echo (for testing)",
}


class CommandStep(BaseStep):
    """
    Executes a shell command from an allowlist.

    Commands can use template variables from the context.
    """

    def __init__(
        self,
        step_id: str,
        command: list[str],
        name: Optional[str] = None,
        description: Optional[str] = None,
        depends_on: Optional[list[str]] = None,
        timeout: int = 60,
        capture_output: bool = True,
    ):
        """
        Initialize the command step.

        Args:
            step_id: Step identifier
            command: Command and arguments as list
            name: Human-readable name
            description: Description shown during execution
            depends_on: Step dependencies
            timeout: Command timeout in seconds
            capture_output: Whether to capture stdout/stderr
        """
        super().__init__(step_id, name, description, depends_on)
        self.command = command
        self.timeout = timeout
        self.capture_output = capture_output

    def execute(self, context: WorkflowContext) -> StepResult:
        """Execute the shell command."""
        context.report_progress(
            self.description or f"Running {self.name}..."
        )

        # Validate command
        if not self.command:
            return StepResult.fail("No command specified")

        # Check if command is allowed
        base_cmd = self.command[0].split("/")[-1]  # Get basename
        if base_cmd not in ALLOWED_COMMANDS:
            return StepResult.fail(
                f"Command not allowed: {base_cmd}. "
                f"Allowed commands: {list(ALLOWED_COMMANDS.keys())}"
            )

        # Process template variables in command
        variables = context.get_all_variables()
        processed_cmd = []
        for arg in self.command:
            processed = TemplateProcessor.process(arg, variables)
            processed_cmd.append(processed)

        try:
            result = subprocess.run(
                processed_cmd,
                capture_output=self.capture_output,
                text=True,
                timeout=self.timeout,
                cwd=str(context.temp_dir),
            )

            if result.returncode != 0:
                error_msg = result.stderr or f"Command exited with code {result.returncode}"
                return StepResult.fail(error_msg)

            return StepResult.ok({
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            })

        except subprocess.TimeoutExpired:
            return StepResult.fail(f"Command timed out after {self.timeout} seconds")
        except FileNotFoundError:
            return StepResult.fail(f"Command not found: {processed_cmd[0]}")
        except Exception as e:
            return StepResult.fail(f"Command execution failed: {e}")

    def validate(self, context: WorkflowContext) -> Optional[str]:
        """Validate the command."""
        if not self.command:
            return "No command specified"

        base_cmd = self.command[0].split("/")[-1]
        if base_cmd not in ALLOWED_COMMANDS:
            return f"Command not allowed: {base_cmd}"

        return None
