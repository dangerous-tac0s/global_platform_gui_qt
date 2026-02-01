"""
Script Step

Executes Python code snippets in a sandboxed environment.
"""

import ast
import sys
from typing import Any, Optional

from ..context import WorkflowContext, SandboxedContext
from .base import BaseStep, StepResult, StepError


# Whitelist of allowed imports
ALLOWED_IMPORTS = {
    "cryptography": "cryptography",
    "cryptography.hazmat.primitives": "cryptography.hazmat.primitives",
    "cryptography.hazmat.primitives.asymmetric": "cryptography.hazmat.primitives.asymmetric",
    "cryptography.hazmat.primitives.asymmetric.ec": "cryptography.hazmat.primitives.asymmetric.ec",
    "cryptography.hazmat.primitives.asymmetric.rsa": "cryptography.hazmat.primitives.asymmetric.rsa",
    "cryptography.hazmat.primitives.serialization": "cryptography.hazmat.primitives.serialization",
    "cryptography.hazmat.primitives.hashes": "cryptography.hazmat.primitives.hashes",
    "cryptography.hazmat.backends": "cryptography.hazmat.backends",
    "cryptography.x509": "cryptography.x509",
    "hashlib": "hashlib",
    "struct": "struct",
    "binascii": "binascii",
    "base64": "base64",
    "json": "json",
    "datetime": "datetime",
    "os.path": "os.path",
    "tempfile": "tempfile",
}

# Blocked function names
BLOCKED_NAMES = {
    "exec", "eval", "compile", "__import__",
    "open", "file", "input",
    "globals", "locals", "vars",
    "getattr", "setattr", "delattr",
    "exit", "quit",
}


class ScriptStep(BaseStep):
    """
    Executes a Python script in a sandboxed environment.

    The script has access to:
    - context: SandboxedContext for variable access
    - field_values: Dict of form field values
    - Standard safe built-ins

    The script should store its result in context.set() or
    modify the 'result' variable.
    """

    def __init__(
        self,
        step_id: str,
        script: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        depends_on: Optional[list[str]] = None,
    ):
        """
        Initialize the script step.

        Args:
            step_id: Step identifier
            script: Python code to execute
            name: Human-readable name
            description: Description shown during execution
            depends_on: Step dependencies
        """
        super().__init__(step_id, name, description, depends_on)
        self.script = script

    def execute(self, context: WorkflowContext) -> StepResult:
        """Execute the Python script."""
        context.report_progress(
            self.description or f"Executing {self.name}..."
        )

        # Validate script before execution
        validation_error = self._validate_script()
        if validation_error:
            return StepResult.fail(f"Script validation failed: {validation_error}")

        try:
            result = self._execute_sandboxed(context)
            return StepResult.ok(result)
        except Exception as e:
            return StepResult.fail(f"Script execution failed: {e}")

    def _validate_script(self) -> Optional[str]:
        """Validate the script for safety."""
        try:
            tree = ast.parse(self.script)
        except SyntaxError as e:
            return f"Syntax error: {e}"

        # Check for blocked names
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                if node.id in BLOCKED_NAMES:
                    return f"Blocked function: {node.id}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name not in ALLOWED_IMPORTS:
                        return f"Import not allowed: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module not in ALLOWED_IMPORTS:
                    # Check if it's a submodule of an allowed import
                    allowed = False
                    for allowed_mod in ALLOWED_IMPORTS:
                        if module.startswith(allowed_mod + ".") or module == allowed_mod:
                            allowed = True
                            break
                    if not allowed:
                        return f"Import not allowed: {module}"

        return None

    def _execute_sandboxed(self, context: WorkflowContext) -> Any:
        """Execute the script in a sandboxed environment."""
        # Create sandboxed context
        sandboxed = SandboxedContext(context)

        # Build safe globals
        safe_globals = self._build_safe_globals()

        # Build locals with context access
        local_vars = {
            "context": sandboxed,
            "field_values": context.get_all_variables(),
            "result": None,
        }

        # Execute the script
        exec(self.script, safe_globals, local_vars)

        # Return the result
        return local_vars.get("result")

    def _build_safe_globals(self) -> dict:
        """Build a safe globals dictionary."""
        safe_builtins = {
            # Safe built-in functions
            "abs": abs,
            "all": all,
            "any": any,
            "bin": bin,
            "bool": bool,
            "bytearray": bytearray,
            "bytes": bytes,
            "chr": chr,
            "dict": dict,
            "divmod": divmod,
            "enumerate": enumerate,
            "filter": filter,
            "float": float,
            "format": format,
            "frozenset": frozenset,
            "hex": hex,
            "int": int,
            "isinstance": isinstance,
            "issubclass": issubclass,
            "iter": iter,
            "len": len,
            "list": list,
            "map": map,
            "max": max,
            "min": min,
            "next": next,
            "oct": oct,
            "ord": ord,
            "pow": pow,
            "print": print,
            "range": range,
            "repr": repr,
            "reversed": reversed,
            "round": round,
            "set": set,
            "slice": slice,
            "sorted": sorted,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "type": type,
            "zip": zip,
            # Constants
            "True": True,
            "False": False,
            "None": None,
            # Exceptions for control flow
            "Exception": Exception,
            "ValueError": ValueError,
            "TypeError": TypeError,
            "KeyError": KeyError,
            "IndexError": IndexError,
            "RuntimeError": RuntimeError,
        }

        # Add a custom __import__ that only allows whitelisted modules
        def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name in ALLOWED_IMPORTS:
                return __import__(name, globals, locals, fromlist, level)
            # Check if it's a submodule of an allowed module
            for allowed in ALLOWED_IMPORTS:
                if name.startswith(allowed + ".") or name == allowed:
                    return __import__(name, globals, locals, fromlist, level)
            raise ImportError(f"Import not allowed: {name}")

        safe_builtins["__import__"] = safe_import

        return {"__builtins__": safe_builtins}

    def validate(self, context: WorkflowContext) -> Optional[str]:
        """Validate the script."""
        return self._validate_script()
