"""
Visual Plugin Designer

A multi-page wizard for creating YAML plugin definitions through a graphical interface.
"""

from .wizard import PluginDesignerWizard
from .source_page import SourceConfigPage
from .metadata_page import MetadataPage
from .ui_builder_page import UIBuilderPage
from .action_builder_page import ActionBuilderPage
from .workflow_builder_page import WorkflowBuilderPage
from .yaml_preview import YamlPreviewPane

__all__ = [
    "PluginDesignerWizard",
    "SourceConfigPage",
    "MetadataPage",
    "UIBuilderPage",
    "ActionBuilderPage",
    "WorkflowBuilderPage",
    "YamlPreviewPane",
]
