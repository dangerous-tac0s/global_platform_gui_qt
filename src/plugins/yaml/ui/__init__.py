"""
UI Generation Components

Provides widget creation and dialog building from YAML field definitions.
"""

from .field_factory import (
    FieldWidget,
    FieldFactory,
    ConditionalFieldManager,
    CrossFieldValidator,
)

from .dialog_builder import (
    FormWidget,
    TabbedFormWidget,
    PluginDialog,
    DialogBuilder,
)

__all__ = [
    # Field Factory
    "FieldWidget",
    "FieldFactory",
    "ConditionalFieldManager",
    "CrossFieldValidator",
    # Dialog Builder
    "FormWidget",
    "TabbedFormWidget",
    "PluginDialog",
    "DialogBuilder",
]
