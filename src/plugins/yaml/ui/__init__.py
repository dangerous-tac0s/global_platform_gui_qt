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

from .state_monitor import (
    StateParser,
    StateMonitor,
    StateDisplayWidget,
    StateReaderDefinition,
    ParsedState,
)

from .management_panel import (
    ActionDefinition,
    ActionButton,
    ManagementPanel,
    ManagementDialog,
    create_management_panel_from_schema,
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
    # State Monitor
    "StateParser",
    "StateMonitor",
    "StateDisplayWidget",
    "StateReaderDefinition",
    "ParsedState",
    # Management Panel
    "ActionDefinition",
    "ActionButton",
    "ManagementPanel",
    "ManagementDialog",
    "create_management_panel_from_schema",
]
