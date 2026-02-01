"""
YAML Plugin System

A declarative, YAML-based plugin system for defining JavaCard applets
without writing Python code. Supports:
- CAP file sources (HTTP, local, GitHub releases)
- Installation parameter UIs (forms, tabs, field validation)
- Post-installation management UIs (actions, state monitoring)
- Multi-step workflows (scripts, commands, APDUs)
- Import/export for sharing plugins
"""

from .schema import (
    PluginSchema,
    PluginInfo,
    AppletDefinition,
    AppletMetadata,
    SourceDefinition,
    SourceType,
    FieldType,
    FieldDefinition,
    InstallUIDefinition,
    ManagementUIDefinition,
    ManagementAction,
    WorkflowDefinition,
    WorkflowStep,
    StepType,
    CURRENT_SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
)

from .parser import YamlPluginParser, YamlParseError

from .adapter import YamlPluginAdapter, ValidationError

from .loader import (
    YamlPluginLoader,
    discover_yaml_plugins,
    load_yaml_plugin,
)

from .logging import (
    logger,
    configure_logging,
    set_debug_enabled,
    is_debug_enabled,
)

__all__ = [
    # Schema classes
    "PluginSchema",
    "PluginInfo",
    "AppletDefinition",
    "AppletMetadata",
    "SourceDefinition",
    "SourceType",
    "FieldType",
    "FieldDefinition",
    "InstallUIDefinition",
    "ManagementUIDefinition",
    "ManagementAction",
    "WorkflowDefinition",
    "WorkflowStep",
    "StepType",
    # Constants
    "CURRENT_SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    # Parser
    "YamlPluginParser",
    "YamlParseError",
    # Adapter
    "YamlPluginAdapter",
    "ValidationError",
    # Loader
    "YamlPluginLoader",
    "discover_yaml_plugins",
    "load_yaml_plugin",
    # Logging
    "logger",
    "configure_logging",
    "set_debug_enabled",
    "is_debug_enabled",
]
