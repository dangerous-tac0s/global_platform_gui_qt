# /repos/flexsecure_applets/__init__.py

"""
This __init__.py makes /repos/flexsecureapplets/ a Python package.
Here, we can store shared variables, functions, or imports
that other code can access by importing 'repos.flexsecureapplets'.
"""

# The GitHub info for the entire 'flexsecureapplets' repo
OWNER = "DangerousThings"
REPO_NAME = "flexsecure-applets"

# A dictionary of recognized .cap => AID for this entire repo
FLEXSECURE_AID_MAP = {
    # Just some examples, you can fill in with your real data
    "openjavacard-ndef-full.cap": "D2760000850101",
    "FIDO2.cap": "A0000006472F000101",
    # ...
}

# If you have a function that fetches the latest release from
# 'flexsecure-applets', you could define it here, so your main code
# can do: from repos.flexsecure_applets import fetch_flexsecure_latest_release

def fetch_flexsecure_latest_release():
    """
    Example function that hits the GH API for flexsecure-applets only.
    A specialized version of your 'fetch_latest_release_assets'.
    """
    import requests
    url = f"https://api.github.com/repos/{OWNER}/{REPO_NAME}/releases/latest"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    assets = data.get("assets", [])
    results = {}
    for asset in assets:
        name = asset["name"]
        download_url = asset["browser_download_url"]
        results[name] = download_url
    return results

# If you want to re-export your plugin classes here, for example:
from .openjavacardndef_full import OpenJavaCardNDEFPlugin
# from .fido2 import Fido2Plugin
# etc.
# Then other code can do:
#   from repos.flexsecure_applets import OpenJavaCardNDEFPlugin
#
# But this is optional, depending how you want to structure your imports.
