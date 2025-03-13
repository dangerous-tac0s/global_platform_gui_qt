# /repos/flexsecure_applets/__init__.py

import os
import importlib
import requests

from base_plugin import BaseAppletPlugin

"""
flexsecure-applets plugin: Manages all .cap files and their associated AIDs for the
'DangerousThings/flexsecure-applets' GitHub repository. This plugin expects every
applet to have an entry in the AID map.
"""

# AID map: maps cap filenames to their corresponding AID strings.
FLEXSECURE_AID_MAP = {
    "javacard-memory.cap":         "A0000008466D656D6F727901",
    "keycard.cap":                 "A0000008040001",
    "openjavacard-ndef-full.cap":  "D2760000850101",
    "SatoChip.cap":                "5361746F4368697000",
    "Satodime.cap":                "5361746F44696D6500",
    "SeedKeeper.cap":              "536565644B656570657200",
    "SmartPGPApplet-default.cap":  "D276000124010304000A000000000000",
    "U2FApplet.cap":               "A0000006472F0002",
    "vivokey-otp.cap":             "A0000005272101014150455801",
    "YkHMACApplet.cap":            "A000000527200101"
}

# GitHub repository information for this plugin.
OWNER = "DangerousThings"
REPO_NAME = "flexsecure-applets"

# Dictionary to store per-cap override classes.
override_map = {}

def fetch_flexsecure_latest_release() -> dict[str, str]:
    """
    Fetch the latest release from GitHub for the 'DangerousThings/flexsecure-applets' repo.
    Returns a dict mapping { cap_filename: download_url } for assets recognized in FLEXSECURE_AID_MAP.
    """
    url = f"https://api.github.com/repos/{OWNER}/{REPO_NAME}/releases/latest"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    assets = data.get("assets", [])
    results = {}
    for asset in assets:
        name = asset["name"]
        dl_url = asset["browser_download_url"]
        if name in FLEXSECURE_AID_MAP:
            results[name] = dl_url
    return results

class FlexsecureAppletsPlugin(BaseAppletPlugin):
    """
    The single plugin for the entire 'flexsecure-applets' repository.
    It uses FLEXSECURE_AID_MAP to associate CAP filenames with AIDs and delegates
    any specialized logic (pre_install, dialog, post_install) to per-cap overrides
    if one exists.
    """
    def __init__(self):
        super().__init__()
        self._selected_cap = None
        self._override_instance = None
        self.auto_import_plugins('flexsecure-applets')

    @property
    def name(self) -> str:
        return "flexsecure-applets"

    def fetch_available_caps(self) -> dict[str, str]:
        return fetch_flexsecure_latest_release()

    def set_cap_name(self, cap_name: str):
        """
        Called when a .cap is selected for install/uninstall.
        If an override is registered for this cap, instantiate it.
        """
        self._selected_cap = cap_name
        if cap_name in override_map:
            override_cls = override_map[cap_name]
            self._override_instance = override_cls()
        else:
            self._override_instance = None

    def get_cap_filename(self) -> str:
        return self._selected_cap or ""

    def get_aid_for_cap(self, cap_name: str) -> str | None:
        return FLEXSECURE_AID_MAP.get(cap_name)

    def get_cap_for_aid(self, raw_aid: str) -> str | None:
        norm = raw_aid.upper().replace(" ", "")
        for c, a in FLEXSECURE_AID_MAP.items():
            if a.upper().replace(" ", "") == norm:
                return c
        return None

    def get_aid_list(self) -> list[str]:
        if not self._selected_cap:
            return []
        a = self.get_aid_for_cap(self._selected_cap)
        return [a] if a else []

    def pre_install(self, **kwargs):
        if self._override_instance:
            self._override_instance.pre_install(self, **kwargs)

    def post_install(self, **kwargs):
        if self._override_instance:
            self._override_instance.post_install(self, **kwargs)

    def create_dialog(self, parent=None):
        if self._override_instance:
            return self._override_instance.create_dialog(self, parent)
        return None

    def get_result(self):
        if self._override_instance:
            return self._override_instance.get_result()
        return {}
