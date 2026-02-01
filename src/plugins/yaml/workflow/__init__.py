"""
Workflow Engine

Provides multi-step workflow execution for complex applet operations.
"""

from .context import WorkflowContext, SandboxedContext
from .engine import WorkflowEngine, WorkflowBuilder, WorkflowError
from .steps import (
    BaseStep,
    StepResult,
    StepError,
    ScriptStep,
    CommandStep,
    ApduStep,
    DialogStep,
    ConfirmationStep,
)

__all__ = [
    # Context
    "WorkflowContext",
    "SandboxedContext",
    # Engine
    "WorkflowEngine",
    "WorkflowBuilder",
    "WorkflowError",
    # Steps
    "BaseStep",
    "StepResult",
    "StepError",
    "ScriptStep",
    "CommandStep",
    "ApduStep",
    "DialogStep",
    "ConfirmationStep",
]
