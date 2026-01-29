"""
AppletController - Manages applet installation and uninstallation workflows.

This controller orchestrates:
- Applet listing and availability
- Storage validation before install
- Mutual exclusivity checks
- Installation/uninstallation workflows
- Plugin integration

Events Emitted:
- InstalledAppsUpdatedEvent - installed apps list changed
- OperationResultEvent - install/uninstall complete
- ProgressEvent - operation progress
- ErrorEvent - operation failures
"""

from typing import Optional, Dict, List, Callable, Any, TYPE_CHECKING
from dataclasses import dataclass

from ..models.applet import (
    AppletInfo,
    InstalledApplet,
    InstallResult,
    InstallStatus,
    StorageRequirement,
)
from ..models.card import CardMemory
from ..events.event_bus import (
    EventBus,
    InstalledAppsUpdatedEvent,
    OperationResultEvent,
    ProgressEvent,
    ErrorEvent,
    StatusMessageEvent,
)

if TYPE_CHECKING:
    from ..services.interfaces import IGPService


# Known unsupported apps that should be filtered out
UNSUPPORTED_APPS = ["FIDO2.cap", "openjavacard-ndef-tiny.cap", "keycard.cap"]

# Known mutual exclusivity rules
MUTUAL_EXCLUSIVITY_RULES = {
    # U2F and FIDO2 conflict
    "U2F.cap": {"FIDO2.cap"},
    "vivokey-u2f.cap": {"FIDO2.cap"},
}


@dataclass
class PluginInfo:
    """Information about an applet plugin."""
    name: str
    plugin_class: Any
    caps: Dict[str, str]  # cap_name -> download_url
    descriptions: Dict[str, str]  # cap_name -> markdown description
    storage: Dict[str, Dict[str, int]]  # cap_name -> {persistent, transient}


class AppletController:
    """
    Controller for applet installation and management.

    Coordinates between:
    - Plugin system (available apps)
    - GPService (installation commands)
    - CardController (card state, key)
    - UI (via EventBus events)
    """

    def __init__(
        self,
        gp_service: Optional["IGPService"] = None,
        event_bus: Optional[EventBus] = None,
    ):
        """
        Initialize the AppletController.

        Args:
            gp_service: Service for GlobalPlatformPro operations
            event_bus: EventBus instance (uses singleton if not provided)
        """
        self._gp_service = gp_service
        self._bus = event_bus or EventBus.instance()

        # Available apps from plugins
        self._available_apps: Dict[str, AppletInfo] = {}

        # Plugin registry
        self._plugins: Dict[str, PluginInfo] = {}

        # Currently installed apps (AID -> version)
        self._installed_apps: Dict[str, Optional[str]] = {}
        self._installed_cap_names: List[str] = []

        # Current operation state
        self._current_plugin: Optional[Any] = None
        self._operation_in_progress: bool = False

    @property
    def available_apps(self) -> Dict[str, AppletInfo]:
        """Get available apps dictionary."""
        return self._available_apps

    @property
    def installed_apps(self) -> Dict[str, Optional[str]]:
        """Get installed apps (AID -> version)."""
        return self._installed_apps

    @property
    def installed_cap_names(self) -> List[str]:
        """Get list of installed CAP file names."""
        return self._installed_cap_names

    # =========================================================================
    # Plugin Management
    # =========================================================================

    def register_plugin(
        self,
        name: str,
        plugin_class: Any,
        caps: Dict[str, str],
        descriptions: Dict[str, str],
        storage: Dict[str, Dict[str, int]],
    ) -> None:
        """
        Register a plugin with the controller.

        Args:
            name: Plugin name
            plugin_class: Plugin class for instantiation
            caps: Dict mapping cap_name to download_url
            descriptions: Dict mapping cap_name to markdown description
            storage: Dict mapping cap_name to storage requirements
        """
        self._plugins[name] = PluginInfo(
            name=name,
            plugin_class=plugin_class,
            caps=caps,
            descriptions=descriptions,
            storage=storage,
        )

        # Add to available apps
        for cap_name, url in caps.items():
            if cap_name in UNSUPPORTED_APPS:
                continue

            storage_reqs = storage.get(cap_name, {})
            self._available_apps[cap_name] = AppletInfo(
                cap_name=cap_name,
                aid="",  # Will be resolved via plugin
                plugin_name=name,
                download_url=url,
                description_md=descriptions.get(cap_name),
                storage_persistent=storage_reqs.get("persistent"),
                storage_transient=storage_reqs.get("transient"),
                mutual_exclusion=MUTUAL_EXCLUSIVITY_RULES.get(cap_name, set()),
                unsupported=(cap_name in UNSUPPORTED_APPS),
            )

    def get_plugin_instance(self, plugin_name: str) -> Optional[Any]:
        """Get a new instance of a plugin."""
        if plugin_name in self._plugins:
            return self._plugins[plugin_name].plugin_class()
        return None

    # =========================================================================
    # Availability and Filtering
    # =========================================================================

    def get_available_applets(self) -> List[str]:
        """
        Get list of available applet CAP names.

        Filters out:
        - Unsupported apps
        - Already installed apps

        Returns:
            List of cap_name strings
        """
        available = []
        for cap_name, info in self._available_apps.items():
            if info.unsupported:
                continue
            if cap_name in self._installed_cap_names:
                continue
            available.append(cap_name)
        return sorted(available)

    def get_applet_info(self, cap_name: str) -> Optional[AppletInfo]:
        """Get info for an available applet."""
        return self._available_apps.get(cap_name)

    def get_applet_description(self, cap_name: str) -> Optional[str]:
        """Get markdown description for an applet."""
        info = self._available_apps.get(cap_name)
        return info.description_md if info else None

    # =========================================================================
    # Validation
    # =========================================================================

    def validate_install(
        self,
        cap_name: str,
        card_memory: Optional[CardMemory] = None,
    ) -> InstallResult:
        """
        Validate if an applet can be installed.

        Checks:
        - Mutual exclusivity rules
        - Storage requirements

        Args:
            cap_name: Name of CAP file to install
            card_memory: Current card memory info

        Returns:
            InstallResult with validation status
        """
        info = self._available_apps.get(cap_name)
        if not info:
            return InstallResult(
                status=InstallStatus.FAILED,
                message=f"Unknown applet: {cap_name}",
            )

        # Check mutual exclusivity
        for conflict in info.mutual_exclusion:
            if conflict in self._installed_cap_names:
                return InstallResult(
                    status=InstallStatus.BLOCKED_MUTUAL_EXCLUSION,
                    message=f"Cannot install {cap_name}: conflicts with installed {conflict}",
                )

        # Additional mutual exclusivity check for U2F/FIDO2
        if "U2F" in cap_name and "FIDO2.cap" in self._installed_cap_names:
            return InstallResult(
                status=InstallStatus.BLOCKED_MUTUAL_EXCLUSION,
                message="FIDO2 falls back to U2F--you do not need both.",
            )

        # Check storage requirements
        if card_memory and card_memory.is_available:
            if info.storage_persistent is not None:
                if card_memory.persistent_free < info.storage_persistent:
                    needed = info.storage_persistent - card_memory.persistent_free
                    return InstallResult(
                        status=InstallStatus.BLOCKED_INSUFFICIENT_STORAGE,
                        message=f"Insufficient persistent storage. Need {needed} more bytes.",
                    )

            if info.storage_transient is not None:
                available_transient = max(
                    card_memory.transient_reset,
                    card_memory.transient_deselect,
                )
                if available_transient > 0 and available_transient < info.storage_transient:
                    needed = info.storage_transient - available_transient
                    return InstallResult(
                        status=InstallStatus.BLOCKED_INSUFFICIENT_STORAGE,
                        message=f"Insufficient transient storage. Need {needed} more bytes.",
                    )

        # All checks passed
        return InstallResult(
            status=InstallStatus.SUCCESS,
            message="Validation passed",
        )

    # =========================================================================
    # Installation
    # =========================================================================

    def prepare_install(
        self,
        cap_name: str,
        card_memory: Optional[CardMemory] = None,
    ) -> InstallResult:
        """
        Prepare for installation (validate and get plugin).

        Args:
            cap_name: Name of CAP file to install
            card_memory: Current card memory info

        Returns:
            InstallResult indicating if install can proceed
        """
        # Validate first
        validation = self.validate_install(cap_name, card_memory)
        if not validation.success and validation.was_blocked:
            self._bus.emit(ErrorEvent(
                message=validation.message,
                recoverable=True,
            ))
            return validation

        # Get plugin info
        info = self._available_apps.get(cap_name)
        if not info:
            return InstallResult(
                status=InstallStatus.FAILED,
                message=f"Unknown applet: {cap_name}",
            )

        # Set current plugin
        plugin = self.get_plugin_instance(info.plugin_name)
        if plugin:
            plugin.set_cap_name(cap_name)
            self._current_plugin = plugin

        self._bus.emit(StatusMessageEvent(
            message=f"Preparing to install: {cap_name}",
            level="info",
        ))

        return InstallResult(
            status=InstallStatus.SUCCESS,
            message="Ready to install",
        )

    def run_pre_install(self, nfc_thread: Any = None) -> Optional[str]:
        """
        Run plugin pre_install hook.

        Args:
            nfc_thread: NFCHandlerThread for plugin access

        Returns:
            Error message if pre_install failed, None if successful
        """
        if self._current_plugin and hasattr(self._current_plugin, 'pre_install'):
            try:
                self._current_plugin.pre_install(nfc_thread=nfc_thread)
                return None
            except Exception as e:
                return f"Pre-install error: {e}"
        return None

    def get_install_dialog(self, parent: Any = None) -> Optional[Any]:
        """
        Get the installation dialog from the current plugin.

        Args:
            parent: Parent widget for dialog

        Returns:
            Dialog instance or None if no dialog needed
        """
        if self._current_plugin and hasattr(self._current_plugin, 'create_dialog'):
            return self._current_plugin.create_dialog(parent)
        return None

    def get_install_params(self) -> Optional[Dict[str, Any]]:
        """Get installation parameters from plugin dialog."""
        if self._current_plugin and hasattr(self._current_plugin, 'get_result'):
            return self._current_plugin.get_result()
        return None

    def on_install_complete(self, success: bool, message: str = "") -> None:
        """
        Called when installation completes.

        Args:
            success: Whether installation succeeded
            message: Result message
        """
        self._operation_in_progress = False

        if success and self._current_plugin:
            # Run post_install hook
            if hasattr(self._current_plugin, 'post_install'):
                try:
                    self._current_plugin.post_install()
                except Exception as e:
                    self._bus.emit(ErrorEvent(
                        message=f"Post-install error: {e}",
                        recoverable=True,
                    ))

        self._bus.emit(OperationResultEvent(
            success=success,
            message=message,
            operation_type="install",
        ))

        self._current_plugin = None

    # =========================================================================
    # Uninstallation
    # =========================================================================

    def prepare_uninstall(self, cap_name: str) -> InstallResult:
        """
        Prepare for uninstallation.

        Args:
            cap_name: Name of CAP file or display name to uninstall

        Returns:
            InstallResult indicating if uninstall can proceed
        """
        # Handle "Unknown: <AID>" format
        if "Unknown" in cap_name:
            # Extract AID from format "Unknown: <AID>" or "Unknown from <plugin>: <AID>"
            parts = cap_name.split(" ")
            aid = parts[-1] if len(parts) > 1 else cap_name
            return InstallResult(
                status=InstallStatus.SUCCESS,
                message=f"Ready to uninstall by AID: {aid}",
            )

        # Get plugin info
        info = self._available_apps.get(cap_name)
        if not info:
            return InstallResult(
                status=InstallStatus.FAILED,
                message=f"No plugin info for: {cap_name}",
            )

        # Set current plugin
        plugin = self.get_plugin_instance(info.plugin_name)
        if plugin:
            plugin.set_cap_name(cap_name)
            self._current_plugin = plugin

            # Run pre_uninstall hook
            if hasattr(plugin, 'pre_uninstall'):
                try:
                    plugin.pre_uninstall()
                except Exception as e:
                    return InstallResult(
                        status=InstallStatus.FAILED,
                        message=f"Pre-uninstall error: {e}",
                    )

        self._bus.emit(StatusMessageEvent(
            message=f"Preparing to uninstall: {cap_name}",
            level="info",
        ))

        return InstallResult(
            status=InstallStatus.SUCCESS,
            message="Ready to uninstall",
        )

    def get_fallback_aid(self) -> Optional[str]:
        """Get fallback AID from current plugin for uninstall."""
        if self._current_plugin and hasattr(self._current_plugin, 'get_aid_list'):
            aids = self._current_plugin.get_aid_list()
            return aids[0] if aids else None
        return None

    def on_uninstall_complete(self, success: bool, message: str = "") -> None:
        """Called when uninstallation completes."""
        self._operation_in_progress = False

        self._bus.emit(OperationResultEvent(
            success=success,
            message=message,
            operation_type="uninstall",
        ))

        self._current_plugin = None

    # =========================================================================
    # Installed Apps Tracking
    # =========================================================================

    def update_installed_apps(
        self,
        installed_aids: Dict[str, Optional[str]],
    ) -> None:
        """
        Update the list of installed apps from card scan.

        Args:
            installed_aids: Dict mapping AID to version (or None)
        """
        self._installed_apps = installed_aids
        self._installed_cap_names = []

        # Resolve AIDs to cap names via plugins
        for aid in installed_aids.keys():
            cap_name = self._resolve_aid_to_cap(aid)
            if cap_name:
                self._installed_cap_names.append(cap_name)

        # Emit event
        self._bus.emit(InstalledAppsUpdatedEvent(apps=installed_aids))

    def _resolve_aid_to_cap(self, aid: str) -> Optional[str]:
        """Resolve an AID to a cap name using plugins."""
        norm_aid = aid.upper().replace(" ", "")

        for plugin_name, plugin_info in self._plugins.items():
            plugin = plugin_info.plugin_class()
            if hasattr(plugin, 'get_cap_for_aid'):
                cap = plugin.get_cap_for_aid(aid)
                if cap:
                    return cap
            elif hasattr(plugin, 'get_aid_list'):
                for plugin_aid in plugin.get_aid_list():
                    if plugin_aid.upper().replace(" ", "") == norm_aid:
                        # Found match but no cap mapping - return plugin name
                        return None

        return None

    def get_installed_display_info(self) -> List[Dict[str, str]]:
        """
        Get display info for installed apps.

        Returns:
            List of dicts with 'display_name', 'aid', 'version', 'cap_name', 'plugin_name'
        """
        result = []

        for aid, version in self._installed_apps.items():
            norm_aid = aid.upper().replace(" ", "")
            cap_name = None
            plugin_name = None

            # Try to resolve via plugins
            for pname, pinfo in self._plugins.items():
                plugin = pinfo.plugin_class()
                if hasattr(plugin, 'get_cap_for_aid'):
                    cap = plugin.get_cap_for_aid(aid)
                    if cap:
                        cap_name = cap
                        plugin_name = pname
                        break

            if cap_name:
                display_name = cap_name
            elif plugin_name:
                display_name = f"Unknown from {plugin_name}: {aid}"
            else:
                display_name = f"Unknown: {aid}"

            result.append({
                'display_name': display_name,
                'aid': aid,
                'version': version,
                'cap_name': cap_name,
                'plugin_name': plugin_name,
            })

        return result

    # =========================================================================
    # Download Info
    # =========================================================================

    def get_download_url(self, cap_name: str) -> Optional[str]:
        """Get download URL for a CAP file."""
        info = self._available_apps.get(cap_name)
        return info.download_url if info else None

    def get_plugin_name(self, cap_name: str) -> Optional[str]:
        """Get plugin name for a CAP file."""
        info = self._available_apps.get(cap_name)
        return info.plugin_name if info else None
