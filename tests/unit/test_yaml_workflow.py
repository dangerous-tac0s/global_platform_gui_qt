"""
Unit tests for YAML Plugin Workflow Engine

Tests the WorkflowEngine, WorkflowContext, and step implementations.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from src.plugins.yaml.workflow.context import WorkflowContext, SandboxedContext
from src.plugins.yaml.workflow.engine import WorkflowEngine, WorkflowBuilder, WorkflowError
from src.plugins.yaml.workflow.steps.base import BaseStep, StepResult, StepError
from src.plugins.yaml.workflow.steps.script_step import ScriptStep
from src.plugins.yaml.workflow.steps.command_step import CommandStep
from src.plugins.yaml.workflow.steps.apdu_step import ApduStep
from src.plugins.yaml.workflow.steps.dialog_step import DialogStep, ConfirmationStep


class TestWorkflowContext:
    """Tests for WorkflowContext class."""

    def test_init_empty(self):
        """Test creating an empty context."""
        ctx = WorkflowContext()
        assert ctx.get("nonexistent") is None
        assert ctx.get("nonexistent", "default") == "default"

    def test_init_with_values(self):
        """Test creating context with initial values."""
        ctx = WorkflowContext(initial_values={"key1": "value1", "key2": 42})
        assert ctx.get("key1") == "value1"
        assert ctx.get("key2") == 42

    def test_set_and_get(self):
        """Test setting and getting values."""
        ctx = WorkflowContext()
        ctx.set("test_key", "test_value")
        assert ctx.get("test_key") == "test_value"

    def test_step_results(self):
        """Test storing and retrieving step results."""
        ctx = WorkflowContext()
        ctx.set_step_result("step1", {"output": "data"})

        assert ctx.get_step_result("step1") == {"output": "data"}
        # Step results should also be accessible via get()
        assert ctx.get("step1") == {"output": "data"}
        # And via _result suffix
        assert ctx.get("step1_result") == {"output": "data"}

    def test_get_all_variables(self):
        """Test getting all variables including step results."""
        ctx = WorkflowContext(initial_values={"var1": "a"})
        ctx.set("var2", "b")
        ctx.set_step_result("step1", "result1")

        all_vars = ctx.get_all_variables()
        assert all_vars["var1"] == "a"
        assert all_vars["var2"] == "b"
        assert all_vars["step1"] == "result1"

    def test_temp_dir(self):
        """Test temporary directory creation."""
        ctx = WorkflowContext()
        temp_dir = ctx.temp_dir
        assert temp_dir.exists()
        assert temp_dir.is_dir()

    def test_create_temp_file(self):
        """Test creating a temporary file."""
        ctx = WorkflowContext()
        file_path = ctx.create_temp_file("test.txt", b"Hello World")

        assert file_path.exists()
        assert file_path.read_bytes() == b"Hello World"

    def test_progress_callback(self):
        """Test progress reporting."""
        callback = Mock()
        ctx = WorkflowContext(progress_callback=callback)

        ctx.report_progress("Testing", 50.0)

        callback.assert_called_once_with("Testing", 50.0)

    def test_cancellation(self):
        """Test cancellation flag."""
        ctx = WorkflowContext()
        assert not ctx.is_cancelled

        ctx.cancel()
        assert ctx.is_cancelled

    def test_register_service(self):
        """Test service registration."""
        ctx = WorkflowContext()
        mock_service = Mock()

        ctx.register_service("test_service", mock_service)

        assert ctx.get_service("test_service") is mock_service
        assert ctx.get_service("unknown") is None

    def test_cleanup(self):
        """Test cleanup of temporary files."""
        ctx = WorkflowContext()
        temp_dir = ctx.temp_dir
        ctx.create_temp_file("test.txt", b"data")

        ctx.cleanup()

        assert not temp_dir.exists()


class TestSandboxedContext:
    """Tests for SandboxedContext class."""

    def test_get_and_set(self):
        """Test get/set through sandboxed context."""
        ctx = WorkflowContext(initial_values={"key": "value"})
        sandbox = SandboxedContext(ctx)

        assert sandbox.get("key") == "value"
        sandbox.set("new_key", "new_value")
        assert sandbox.get("new_key") == "new_value"

    def test_temp_file_operations(self):
        """Test temp file operations."""
        ctx = WorkflowContext()
        sandbox = SandboxedContext(ctx)

        temp_dir = sandbox.get_temp_dir()
        assert isinstance(temp_dir, str)

        file_path = sandbox.create_temp_file("test.txt", b"data")
        assert isinstance(file_path, str)

    def test_report_progress(self):
        """Test progress reporting from sandbox."""
        callback = Mock()
        ctx = WorkflowContext(progress_callback=callback)
        sandbox = SandboxedContext(ctx)

        sandbox.report_progress("Progress message")

        callback.assert_called_once_with("Progress message", -1)


class TestStepResult:
    """Tests for StepResult class."""

    def test_ok_result(self):
        """Test creating a successful result."""
        result = StepResult.ok({"data": "value"})
        assert result.success is True
        assert result.data == {"data": "value"}
        assert result.error is None

    def test_fail_result(self):
        """Test creating a failed result."""
        result = StepResult.fail("Something went wrong")
        assert result.success is False
        assert result.data is None
        assert result.error == "Something went wrong"


class TestScriptStep:
    """Tests for ScriptStep class."""

    def test_simple_script(self):
        """Test executing a simple script."""
        step = ScriptStep(
            step_id="test",
            script='context.set("output", "hello")',
        )
        ctx = WorkflowContext()

        result = step.execute(ctx)

        assert result.success
        assert ctx.get("output") == "hello"

    def test_script_with_result(self):
        """Test script that sets result variable."""
        step = ScriptStep(
            step_id="test",
            script='result = {"computed": 42}',
        )
        ctx = WorkflowContext()

        result = step.execute(ctx)

        assert result.success
        assert result.data == {"computed": 42}

    def test_script_uses_context_values(self):
        """Test script accessing context values."""
        step = ScriptStep(
            step_id="test",
            script='result = context.get("input") * 2',
        )
        ctx = WorkflowContext(initial_values={"input": 21})

        result = step.execute(ctx)

        assert result.success
        assert result.data == 42

    def test_script_with_allowed_imports(self):
        """Test script using allowed imports."""
        step = ScriptStep(
            step_id="test",
            script='import hashlib; result = hashlib.sha256(b"test").hexdigest()[:8]',
        )
        ctx = WorkflowContext()

        result = step.execute(ctx)

        assert result.success
        assert result.data == "9f86d081"

    def test_script_blocks_dangerous_imports(self):
        """Test script blocking dangerous imports."""
        step = ScriptStep(
            step_id="test",
            script='import subprocess; subprocess.run(["ls"])',
        )
        ctx = WorkflowContext()

        result = step.execute(ctx)

        assert not result.success
        assert "not allowed" in result.error.lower() or "blocked" in result.error.lower()

    def test_script_blocks_exec(self):
        """Test script blocking exec()."""
        step = ScriptStep(
            step_id="test",
            script='exec("print(1)")',
        )
        ctx = WorkflowContext()

        result = step.execute(ctx)

        assert not result.success

    def test_script_error_handling(self):
        """Test script error handling."""
        step = ScriptStep(
            step_id="test",
            script='raise ValueError("Test error")',
        )
        ctx = WorkflowContext()

        result = step.execute(ctx)

        assert not result.success
        assert "Test error" in result.error

    def test_script_validation_syntax_error(self):
        """Test script validation catches syntax errors."""
        step = ScriptStep(step_id="test", script="def broken(")

        error = step.validate(WorkflowContext())
        assert error is not None
        assert "syntax" in error.lower()

    def test_empty_script_is_valid(self):
        """Test that empty script passes validation (is a no-op)."""
        step = ScriptStep(step_id="test", script="")

        error = step.validate(WorkflowContext())
        assert error is None  # Empty script is valid Python


class TestCommandStep:
    """Tests for CommandStep class."""

    def test_allowed_command(self):
        """Test executing an allowed command."""
        step = CommandStep(
            step_id="test",
            command=["gp", "--help"],  # Command as list
            capture_output=True,
        )
        ctx = WorkflowContext()

        # Mock subprocess to avoid actual execution
        with patch("src.plugins.yaml.workflow.steps.command_step.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="GlobalPlatformPro help",
                stderr="",
            )
            result = step.execute(ctx)

        assert result.success
        mock_run.assert_called_once()

    def test_blocked_command(self):
        """Test blocking disallowed commands."""
        step = CommandStep(
            step_id="test",
            command=["rm", "-rf", "/"],  # Command as list
        )
        ctx = WorkflowContext()

        result = step.execute(ctx)

        assert not result.success
        assert "not allowed" in result.error.lower()

    def test_command_template_substitution(self):
        """Test template substitution in command."""
        step = CommandStep(
            step_id="test",
            command=["gp", "--install", "{cap_file}"],  # Command as list with template
            capture_output=True,
        )
        ctx = WorkflowContext(initial_values={"cap_file": "/path/to/applet.cap"})

        with patch("src.plugins.yaml.workflow.steps.command_step.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
            step.execute(ctx)

        call_args = mock_run.call_args
        # Check that the template was substituted
        assert "/path/to/applet.cap" in str(call_args)

    def test_command_validation(self):
        """Test command validation."""
        step = CommandStep(step_id="test", command=[])  # Empty list

        error = step.validate(WorkflowContext())
        assert error is not None


class TestApduStep:
    """Tests for ApduStep class."""

    def test_apdu_execution(self):
        """Test APDU execution."""
        step = ApduStep(
            step_id="test",
            apdu="00A4040008D276000124010304",  # Use 'apdu' parameter
        )

        # Mock NFC thread service - returns raw response bytes
        mock_nfc = Mock()
        mock_nfc.send_apdu.return_value = bytes.fromhex("9000")

        ctx = WorkflowContext()
        ctx.register_service("nfc_thread", mock_nfc)

        result = step.execute(ctx)

        assert result.success
        mock_nfc.send_apdu.assert_called_once()

    def test_apdu_with_template(self):
        """Test APDU with template substitution."""
        # Test with a value that needs hex encoding
        step = ApduStep(
            step_id="test",
            apdu="00200081{aid_length:02X}{aid}",  # Length and hex value
        )

        mock_nfc = Mock()
        mock_nfc.send_apdu.return_value = bytes.fromhex("9000")

        # Provide a hex value directly - it won't be re-encoded
        ctx = WorkflowContext(initial_values={"aid": "D276000124010304"})
        ctx.register_service("nfc_thread", mock_nfc)

        result = step.execute(ctx)

        assert result.success
        # Verify the APDU was sent correctly
        call_args = mock_nfc.send_apdu.call_args[0][0]
        # The APDU should contain the AID bytes
        assert bytes.fromhex("D276000124010304") in call_args

    def test_apdu_check_sw_success(self):
        """Test APDU status word checking - success case."""
        step = ApduStep(
            step_id="test",
            apdu="00A4040008D276000124010304",
            expect_sw="9000",  # Use 'expect_sw' (single string)
        )

        mock_nfc = Mock()
        mock_nfc.send_apdu.return_value = bytes.fromhex("9000")

        ctx = WorkflowContext()
        ctx.register_service("nfc_thread", mock_nfc)

        result = step.execute(ctx)
        assert result.success

    def test_apdu_unexpected_sw(self):
        """Test APDU with unexpected status word."""
        step = ApduStep(
            step_id="test",
            apdu="00A4040008D276000124010304",
            expect_sw="9000",  # Use 'expect_sw' (single string)
        )

        mock_nfc = Mock()
        mock_nfc.send_apdu.return_value = bytes.fromhex("6A82")

        ctx = WorkflowContext()
        ctx.register_service("nfc_thread", mock_nfc)

        result = step.execute(ctx)
        assert not result.success
        assert "6A82" in result.error.upper()

    def test_apdu_missing_service(self):
        """Test APDU execution without NFC service."""
        step = ApduStep(
            step_id="test",
            apdu="00A4040008D276000124010304",  # Use 'apdu' parameter
        )
        ctx = WorkflowContext()

        result = step.execute(ctx)
        assert not result.success
        assert "service" in result.error.lower() or "nfc" in result.error.lower()

    def test_apdu_required_services(self):
        """Test that ApduStep requires nfc_thread service."""
        step = ApduStep(step_id="test", apdu="00A4040008D276000124010304")
        assert "nfc_thread" in step.get_required_services()

    def test_apdu_response_data(self):
        """Test that APDU response data is stored correctly."""
        step = ApduStep(
            step_id="test_apdu",
            apdu="00B0000010",  # READ BINARY command
        )

        mock_nfc = Mock()
        # Response: 16 bytes of data + 9000 SW
        mock_nfc.send_apdu.return_value = bytes.fromhex("0102030405060708090A0B0C0D0E0F109000")

        ctx = WorkflowContext()
        ctx.register_service("nfc_thread", mock_nfc)

        result = step.execute(ctx)

        assert result.success
        assert result.data["sw"] == "9000"
        assert result.data["data"] == "0102030405060708090A0B0C0D0E0F10"


class TestWorkflowEngine:
    """Tests for WorkflowEngine class."""

    def test_simple_workflow(self):
        """Test executing a simple workflow."""
        steps = [
            ScriptStep("step1", 'context.set("value", 1)'),
            ScriptStep("step2", 'context.set("value", context.get("value") + 1)'),
            ScriptStep("step3", 'result = context.get("value") + 1'),
        ]

        engine = WorkflowEngine(steps)
        ctx = WorkflowContext()

        results = engine.execute(ctx)

        assert len(results) == 3
        assert all(r.success for r in results.values())
        assert results["step3"].data == 3

    def test_workflow_with_dependencies(self):
        """Test workflow with step dependencies."""
        steps = [
            ScriptStep("step3", 'result = context.get("value")', depends_on=["step2"]),
            ScriptStep("step1", 'context.set("value", 10)'),
            ScriptStep(
                "step2",
                'context.set("value", context.get("value") * 2)',
                depends_on=["step1"],
            ),
        ]

        engine = WorkflowEngine(steps)

        # Verify execution order
        order = engine.get_execution_order()
        assert order.index("step1") < order.index("step2")
        assert order.index("step2") < order.index("step3")

        # Execute and verify results
        ctx = WorkflowContext()
        results = engine.execute(ctx)

        assert results["step3"].data == 20  # 10 * 2

    def test_workflow_circular_dependency(self):
        """Test detection of circular dependencies."""
        steps = [
            ScriptStep("step1", "pass", depends_on=["step2"]),
            ScriptStep("step2", "pass", depends_on=["step3"]),
            ScriptStep("step3", "pass", depends_on=["step1"]),
        ]

        engine = WorkflowEngine(steps)
        errors = engine.validate()

        assert len(errors) > 0
        assert any("circular" in e.lower() for e in errors)

    def test_workflow_missing_dependency(self):
        """Test detection of missing dependencies."""
        steps = [
            ScriptStep("step1", "pass", depends_on=["nonexistent"]),
        ]

        engine = WorkflowEngine(steps)
        errors = engine.validate()

        assert len(errors) > 0
        assert any("nonexistent" in e for e in errors)

    def test_workflow_duplicate_ids(self):
        """Test detection of duplicate step IDs."""
        steps = [
            ScriptStep("same_id", 'context.set("a", 1)'),
            ScriptStep("same_id", 'context.set("b", 2)'),
        ]

        engine = WorkflowEngine(steps)
        errors = engine.validate()

        assert len(errors) > 0
        assert any("duplicate" in e.lower() for e in errors)

    def test_workflow_step_failure(self):
        """Test workflow handling step failure."""
        steps = [
            ScriptStep("step1", 'context.set("value", 1)'),
            ScriptStep("step2", 'raise ValueError("Intentional failure")'),
            ScriptStep("step3", 'context.set("value", 3)'),
        ]

        engine = WorkflowEngine(steps)
        ctx = WorkflowContext()

        with pytest.raises(WorkflowError) as exc_info:
            engine.execute(ctx)

        assert exc_info.value.step_id == "step2"
        assert "Intentional failure" in str(exc_info.value.step_error)

    def test_workflow_cancellation(self):
        """Test workflow cancellation via context."""
        # We can't directly cancel from within a script since SandboxedContext
        # doesn't expose cancel(). Instead, test that external cancellation works.
        ctx = WorkflowContext()
        ctx.cancel()  # Pre-cancel before execution

        steps = [
            ScriptStep("step1", 'result = "should not run"'),
        ]

        engine = WorkflowEngine(steps)

        with pytest.raises(WorkflowError) as exc_info:
            engine.execute(ctx)

        assert "cancelled" in str(exc_info.value).lower()

    def test_workflow_progress_callback(self):
        """Test workflow progress reporting."""
        progress_calls = []

        def callback(message, percent):
            progress_calls.append((message, percent))

        steps = [
            ScriptStep("step1", "pass", name="First Step"),
            ScriptStep("step2", "pass", name="Second Step"),
        ]

        engine = WorkflowEngine(steps, progress_callback=callback)
        engine.execute()

        # Should have progress calls for each step plus completion
        assert len(progress_calls) >= 2
        assert any("completed" in msg.lower() for msg, _ in progress_calls)

    def test_workflow_with_initial_values(self):
        """Test workflow with initial context values."""
        steps = [
            ScriptStep("step1", 'result = context.get("input") * 2'),
        ]

        engine = WorkflowEngine(steps)
        results = engine.execute(initial_values={"input": 21})

        assert results["step1"].data == 42

    def test_workflow_stores_step_results(self):
        """Test that step results are stored in context."""
        steps = [
            ScriptStep("producer", 'result = {"key": "value"}'),
            ScriptStep(
                "consumer",
                # Use the _result suffix to access step result via SandboxedContext.get()
                'result = context.get("producer_result")["key"]',
                depends_on=["producer"],
            ),
        ]

        engine = WorkflowEngine(steps)
        results = engine.execute()

        assert results["consumer"].data == "value"


class TestWorkflowEngineMissingServices:
    """Tests for WorkflowEngine service validation."""

    def test_missing_required_service(self):
        """Test workflow fails when required service is missing."""
        steps = [
            ApduStep("apdu_step", apdu="00A4040008D276000124010304"),
        ]

        engine = WorkflowEngine(steps)
        ctx = WorkflowContext()  # No nfc_thread service registered

        with pytest.raises(WorkflowError) as exc_info:
            engine.execute(ctx)

        assert "nfc_thread" in str(exc_info.value)


class TestDialogStepHeadless:
    """Tests for DialogStep in headless mode."""

    def test_dialog_headless_with_values(self):
        """Test dialog step in headless mode with all values provided."""
        from src.plugins.yaml.schema import FieldDefinition, FieldType

        fields = [
            FieldDefinition(id="field1", type=FieldType.TEXT, label="Field 1"),
            FieldDefinition(
                id="field2", type=FieldType.TEXT, label="Field 2", default="default"
            ),
        ]

        step = DialogStep(step_id="test", fields=fields)

        ctx = WorkflowContext(initial_values={"_headless": True, "field1": "value1"})

        result = step.execute(ctx)

        assert result.success
        assert ctx.get("field1") == "value1"
        assert ctx.get("field2") == "default"

    def test_dialog_headless_missing_required(self):
        """Test dialog step in headless mode with missing required field."""
        from src.plugins.yaml.schema import FieldDefinition, FieldType

        fields = [
            FieldDefinition(
                id="required_field", type=FieldType.TEXT, label="Required", required=True
            ),
        ]

        step = DialogStep(step_id="test", fields=fields)
        ctx = WorkflowContext(initial_values={"_headless": True})

        result = step.execute(ctx)

        assert not result.success
        assert "required_field" in result.error


class TestConfirmationStepHeadless:
    """Tests for ConfirmationStep in headless mode."""

    def test_confirmation_auto_confirms(self):
        """Test confirmation step auto-confirms in headless mode."""
        step = ConfirmationStep(step_id="test", message="Continue?")
        ctx = WorkflowContext(initial_values={"_headless": True})

        result = step.execute(ctx)

        assert result.success


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_full_workflow_with_multiple_step_types(self):
        """Test a workflow combining script and (mocked) APDU steps."""
        steps = [
            ScriptStep(
                "prepare",
                'context.set("aid", "D276000124010304")',
                name="Prepare AID",
            ),
            ScriptStep(
                "compute",
                '''
aid = context.get("aid")
context.set("select_apdu", f"00A40400{len(aid)//2:02X}{aid}")
result = {"ready": True}
''',
                depends_on=["prepare"],
                name="Compute APDU",
            ),
        ]

        engine = WorkflowEngine(steps)
        ctx = WorkflowContext()

        results = engine.execute(ctx)

        assert results["compute"].data == {"ready": True}
        assert ctx.get("select_apdu") == "00A4040008D276000124010304"
