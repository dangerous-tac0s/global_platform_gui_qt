# /repos/flexsecure_applets/__init__.py

import requests

from base_plugin import BaseAppletPlugin

"""
flexsecure_applets plugin: Manages all .cap files and their associated AIDs for the
'DangerousThings/flexsecure_applets' GitHub repository.
"""

# AID map: maps cap filenames to their corresponding AID strings.
FLEXSECURE_AID_MAP = {
    "javacard-memory.cap": "A0000008466D656D6F727901",
    "keycard.cap": "A0000008040001",
    "openjavacard-ndef-full.cap": "D2760000850101",
    "SatoChip.cap": "5361746F4368697000",
    "Satodime.cap": "5361746F44696D6500",
    "SeedKeeper.cap": "536565644B656570657200",
    "SmartPGPApplet-default.cap": "D276000124010304000A000000000000",
    "U2FApplet.cap": "A0000006472F0002",
    "vivokey-otp.cap": "A0000005272101014150455801",
    "YkHMACApplet.cap": "A000000527200101",
}

# GitHub repository information for this plugin.
OWNER = "DangerousThings"
REPO_NAME = "flexsecure-applets"

# Dictionary to store per-cap override classes.
override_map = {}


def fetch_flexsecure_releases() -> list:
    """
    Fetch all releases from GitHub for the 'DangerousThings/flexsecure-applets' repo.

    Returns:
        list: A list of dictionaries, each representing a release, including version, tag, and other details.
    """
    url = f"https://api.github.com/repos/{OWNER}/{REPO_NAME}/releases"

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        releases = []
        for release in data:
            release_info = {
                "tag_name": release.get("tag_name"),
                "name": release.get("name"),
                "published_at": release.get("published_at"),
                "assets": release.get("assets", []),
            }
            releases.append(release_info)

        return releases

    except requests.exceptions.RequestException as e:
        print(f"Error fetching releases: {e}")
        return []


def fetch_flexsecure_release(
    version=None, verbose=False
) -> dict[str, str] or dict[str]:
    """
    Fetch a release from GitHub for the 'DangerousThings/flexsecure-applets' repo.
    Defaults to the latest release if no version is specified.

    Args:
        version (str, optional): The version or tag of the release to fetch. Defaults to None (latest release).

    Returns:
        dict[str, str]: A dictionary with the asset name as the key and download URL as the value.
    """
    if version:
        # If a specific version is requested, fetch that release by tag name
        url = (
            f"https://api.github.com/repos/{OWNER}/{REPO_NAME}/releases/tags/{version}"
        )
    else:
        # If no version is specified, fetch the latest release
        url = f"https://api.github.com/repos/{OWNER}/{REPO_NAME}/releases/latest"

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        assets = data.get("assets", [])

        results = {}
        for asset in assets:
            if ".cap" in asset["name"]:  # Some releases have .jar files
                name = asset["name"]
                dl_url = asset["browser_download_url"]
                # Ensure the asset name is in the FLEXSECURE_AID_MAP if needed
                # if name in FLEXSECURE_AID_MAP:
                results[name] = dl_url

        if verbose:
            return {"apps": results, "version": data["tag_name"]}

        return results

    except requests.exceptions.RequestException as e:
        print(f"Error fetching release: {e}")
        return {}


class FlexsecureAppletsPlugin(BaseAppletPlugin):
    """
    The single plugin for the entire 'flexsecure_applets' repository.
    """

    def __init__(self):
        super().__init__()
        self._selected_cap = None
        self._override_instance = None
        self.auto_import_plugins("flexsecure_applets", override_map)

    @property
    def name(self) -> str:
        return "flexsecure_applets"

    def fetch_available_caps(self, version=None) -> dict[str, str]:
        return fetch_flexsecure_release(version=version)

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
