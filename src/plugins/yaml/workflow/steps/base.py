"""
Base Workflow Step

Abstract base class for all workflow step implementations.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from ..context import WorkflowContext


class StepError(Exception):
    """Exception raised when a workflow step fails."""

    def __init__(self, message: str, step_id: str = "", recoverable: bool = False):
        self.step_id = step_id
        self.recoverable = recoverable
        super().__init__(message)


class StepResult:
    """Result of a workflow step execution."""

    def __init__(
        self,
        success: bool,
        data: Any = None,
        error: Optional[str] = None,
    ):
        self.success = success
        self.data = data
        self.error = error

    @classmethod
    def ok(cls, data: Any = None) -> "StepResult":
        """Create a successful result."""
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str) -> "StepResult":
        """Create a failed result."""
        return cls(success=False, error=error)


class BaseStep(ABC):
    """
    Abstract base class for workflow steps.

    Each step type (script, command, apdu, dialog) should inherit from this
    and implement the execute() method.
    """

    def __init__(
        self,
        step_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        depends_on: Optional[list[str]] = None,
    ):
        """
        Initialize the step.

        Args:
            step_id: Unique identifier for this step
            name: Human-readable name
            description: Description shown during execution
            depends_on: List of step IDs this step depends on
        """
        self.step_id = step_id
        self.name = name or step_id
        self.description = description
        self.depends_on = depends_on or []

    @abstractmethod
    def execute(self, context: WorkflowContext) -> StepResult:
        """
        Execute the step.

        Args:
            context: Workflow context with variables and services

        Returns:
            StepResult indicating success/failure and any output data
        """
        pass

    def validate(self, context: WorkflowContext) -> Optional[str]:
        """
        Validate that the step can be executed.

        Override to add custom validation logic.

        Args:
            context: Workflow context

        Returns:
            Error message if validation fails, None otherwise
        """
        return None

    def get_required_services(self) -> list[str]:
        """
        Get list of required services for this step.

        Override to specify services needed (e.g., "nfc_thread").

        Returns:
            List of service names
        """
        return []

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.step_id!r}, name={self.name!r})"
