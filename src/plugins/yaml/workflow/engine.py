"""
Workflow Engine

Orchestrates the execution of multi-step workflows with dependency resolution,
progress reporting, and error handling.
"""

from collections import deque
from typing import Any, Callable, Optional

from .context import WorkflowContext
from .steps.base import BaseStep, StepResult, StepError


class WorkflowError(Exception):
    """Exception raised when workflow execution fails."""

    def __init__(
        self,
        message: str,
        step_id: Optional[str] = None,
        step_error: Optional[str] = None,
    ):
        self.step_id = step_id
        self.step_error = step_error
        super().__init__(message)


class WorkflowEngine:
    """
    Executes multi-step workflows with dependency resolution.

    Features:
    - Topological ordering based on step dependencies
    - Progress reporting callbacks
    - Cancellation support
    - Step result storage in context
    - Validation before execution
    """

    def __init__(
        self,
        steps: list[BaseStep],
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ):
        """
        Initialize the workflow engine.

        Args:
            steps: List of workflow steps to execute
            progress_callback: Optional callback for progress updates (message, percent)
        """
        self._steps = {step.step_id: step for step in steps}
        self._step_list = steps
        self._progress_callback = progress_callback
        self._execution_order: list[str] = []

    def validate(self) -> list[str]:
        """
        Validate the workflow before execution.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Check for duplicate step IDs
        seen_ids = set()
        for step in self._step_list:
            if step.step_id in seen_ids:
                errors.append(f"Duplicate step ID: {step.step_id}")
            seen_ids.add(step.step_id)

        # Check for missing dependencies
        for step in self._step_list:
            for dep_id in step.depends_on:
                if dep_id not in self._steps:
                    errors.append(
                        f"Step '{step.step_id}' depends on unknown step '{dep_id}'"
                    )

        # Check for circular dependencies
        try:
            self._build_execution_order()
        except WorkflowError as e:
            errors.append(str(e))

        return errors

    def _build_execution_order(self) -> list[str]:
        """
        Build the execution order using topological sort.

        Returns:
            List of step IDs in execution order

        Raises:
            WorkflowError: If circular dependencies are detected
        """
        # Calculate in-degree for each step
        in_degree = {step_id: 0 for step_id in self._steps}
        for step in self._step_list:
            for dep_id in step.depends_on:
                if dep_id in self._steps:
                    in_degree[step.step_id] = in_degree.get(step.step_id, 0) + 1

        # Kahn's algorithm for topological sort
        queue = deque([step_id for step_id, degree in in_degree.items() if degree == 0])
        order = []

        while queue:
            step_id = queue.popleft()
            order.append(step_id)

            # Find steps that depend on this one
            for step in self._step_list:
                if step_id in step.depends_on:
                    in_degree[step.step_id] -= 1
                    if in_degree[step.step_id] == 0:
                        queue.append(step.step_id)

        if len(order) != len(self._steps):
            # Find steps involved in cycle
            remaining = [sid for sid in self._steps if sid not in order]
            raise WorkflowError(
                f"Circular dependency detected involving steps: {remaining}"
            )

        self._execution_order = order
        return order

    def execute(
        self,
        context: Optional[WorkflowContext] = None,
        initial_values: Optional[dict[str, Any]] = None,
    ) -> dict[str, StepResult]:
        """
        Execute the workflow.

        Args:
            context: Optional pre-configured context
            initial_values: Optional initial variable values

        Returns:
            Dictionary mapping step IDs to their results

        Raises:
            WorkflowError: If workflow execution fails
        """
        # Create context if not provided
        if context is None:
            context = WorkflowContext(
                initial_values=initial_values,
                progress_callback=self._progress_callback,
            )
        elif initial_values:
            for key, value in initial_values.items():
                context.set(key, value)

        # Validate workflow
        errors = self.validate()
        if errors:
            raise WorkflowError(f"Workflow validation failed: {'; '.join(errors)}")

        # Build execution order
        self._build_execution_order()

        # Execute steps in order
        results: dict[str, StepResult] = {}
        total_steps = len(self._execution_order)

        for idx, step_id in enumerate(self._execution_order):
            if context.is_cancelled:
                # Report cancellation
                self._report_progress(f"Workflow cancelled at step {step_id}", -1)
                raise WorkflowError("Workflow cancelled by user", step_id=step_id)

            step = self._steps[step_id]

            # Report progress
            percent = (idx / total_steps) * 100
            message = step.description or f"Executing: {step.name}"
            self._report_progress(message, percent)

            # Validate step
            validation_error = step.validate(context)
            if validation_error:
                raise WorkflowError(
                    f"Step validation failed: {validation_error}",
                    step_id=step_id,
                    step_error=validation_error,
                )

            # Check required services
            missing_services = []
            for service_name in step.get_required_services():
                if context.get_service(service_name) is None:
                    missing_services.append(service_name)
            if missing_services:
                raise WorkflowError(
                    f"Missing required services: {', '.join(missing_services)}",
                    step_id=step_id,
                )

            # Execute step
            try:
                result = step.execute(context)
            except StepError as e:
                result = StepResult.fail(str(e))
            except Exception as e:
                result = StepResult.fail(f"Unexpected error: {e}")

            results[step_id] = result

            # Store result in context
            if result.success and result.data is not None:
                context.set_step_result(step_id, result.data)

            # Handle failure
            if not result.success:
                self._report_progress(f"Step '{step.name}' failed: {result.error}", -1)
                raise WorkflowError(
                    f"Step '{step_id}' failed: {result.error}",
                    step_id=step_id,
                    step_error=result.error,
                )

        # Report completion
        self._report_progress("Workflow completed successfully", 100)

        return results

    def _report_progress(self, message: str, percent: float):
        """Report progress to the callback if set."""
        if self._progress_callback:
            self._progress_callback(message, percent)

    def get_step(self, step_id: str) -> Optional[BaseStep]:
        """Get a step by its ID."""
        return self._steps.get(step_id)

    def get_steps(self) -> list[BaseStep]:
        """Get all steps in definition order."""
        return self._step_list.copy()

    def get_execution_order(self) -> list[str]:
        """
        Get the execution order of steps.

        Returns:
            List of step IDs in execution order
        """
        if not self._execution_order:
            self._build_execution_order()
        return self._execution_order.copy()


class WorkflowBuilder:
    """
    Builder for creating workflows from schema definitions.

    Converts WorkflowStep schema objects into executable BaseStep instances.
    """

    def __init__(self):
        self._step_factories: dict[str, Callable] = {}
        self._register_default_factories()

    def _register_default_factories(self):
        """Register the default step type factories."""
        from .steps.script_step import ScriptStep
        from .steps.command_step import CommandStep
        from .steps.apdu_step import ApduStep
        from .steps.dialog_step import DialogStep, ConfirmationStep

        self._step_factories = {
            "script": self._create_script_step,
            "command": self._create_command_step,
            "apdu": self._create_apdu_step,
            "dialog": self._create_dialog_step,
            "confirmation": self._create_confirmation_step,
        }

    def register_step_factory(self, step_type: str, factory: Callable):
        """
        Register a custom step factory.

        Args:
            step_type: Step type identifier
            factory: Factory function that creates the step
        """
        self._step_factories[step_type] = factory

    def build_workflow(
        self,
        workflow_def: "WorkflowDefinition",
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> WorkflowEngine:
        """
        Build a WorkflowEngine from a workflow definition.

        Args:
            workflow_def: Workflow definition from schema
            progress_callback: Optional progress callback

        Returns:
            Configured WorkflowEngine
        """
        steps = []

        for step_def in workflow_def.steps:
            step = self._create_step(step_def)
            if step:
                steps.append(step)

        return WorkflowEngine(steps, progress_callback)

    def _create_step(self, step_def: "WorkflowStep") -> Optional[BaseStep]:
        """Create a step from a step definition."""
        step_type = step_def.type.value if hasattr(step_def.type, "value") else str(step_def.type)

        factory = self._step_factories.get(step_type)
        if factory:
            return factory(step_def)
        return None

    def _create_script_step(self, step_def: "WorkflowStep") -> BaseStep:
        """Create a ScriptStep from definition."""
        from .steps.script_step import ScriptStep

        return ScriptStep(
            step_id=step_def.id,
            script=step_def.script or "",
            name=step_def.name,
            description=step_def.description,
            depends_on=step_def.depends_on,
        )

    def _create_command_step(self, step_def: "WorkflowStep") -> BaseStep:
        """Create a CommandStep from definition."""
        from .steps.command_step import CommandStep

        return CommandStep(
            step_id=step_def.id,
            command=step_def.command or "",
            name=step_def.name,
            description=step_def.description,
            depends_on=step_def.depends_on,
            capture_output=True,
        )

    def _create_apdu_step(self, step_def: "WorkflowStep") -> BaseStep:
        """Create an ApduStep from definition."""
        from .steps.apdu_step import ApduStep

        # Handle expected_sw - take first if it's a list
        expect_sw = None
        if step_def.expected_sw:
            expect_sw = step_def.expected_sw[0] if isinstance(step_def.expected_sw, list) else step_def.expected_sw

        return ApduStep(
            step_id=step_def.id,
            apdu=step_def.apdu or "",
            name=step_def.name,
            description=step_def.description,
            depends_on=step_def.depends_on,
            expect_sw=expect_sw,
        )

    def _create_dialog_step(self, step_def: "WorkflowStep") -> BaseStep:
        """Create a DialogStep from definition."""
        from .steps.dialog_step import DialogStep

        return DialogStep(
            step_id=step_def.id,
            fields=step_def.fields or [],
            name=step_def.name,
            description=step_def.description,
            depends_on=step_def.depends_on,
            title=step_def.name,
        )

    def _create_confirmation_step(self, step_def: "WorkflowStep") -> BaseStep:
        """Create a ConfirmationStep from definition."""
        from .steps.dialog_step import ConfirmationStep

        return ConfirmationStep(
            step_id=step_def.id,
            message=step_def.description or "Continue?",
            name=step_def.name,
            description=step_def.description,
            depends_on=step_def.depends_on,
        )
