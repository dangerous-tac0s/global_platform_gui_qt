# /repos/flexsecure_applets/__init__.py
import json

import requests

from base_plugin import BaseAppletPlugin
from nfc_thread import resource_path

"""
flexsecure_applets plugin: Manages all .cap files and their associated AIDs for the
'DangerousThings/flexsecure_applets' GitHub repository.
"""

# AID map: maps cap filenames to their corresponding AID strings.
FLEXSECURE_AID_MAP = {
    "javacard-memory.cap": "A0000008466D656D6F727901",
    "keycard.cap": "A0000008040001",  # TODO: Add support for selecting apps in multi-app cap
    "openjavacard-ndef-full.cap": "D2760000850101",
    "SatoChip.cap": "5361746F4368697000",
    "Satodime.cap": "5361746F44696D6500",  # This doesn't work with DT/VK products
    "SeedKeeper.cap": "536565644B656570657200",
    "SmartPGPApplet-default.cap": "D276000124010304000A000000000000",
    "SmartPGPApplet-large.cap": "D276000124010304000A000000000000",  # Use this for disgustingly large RSA keys. Consider ECC instead. Seriously.
    "U2FApplet.cap": "A0000006472F0002",
    "FIDO2.cap": "A0000006472F0001",
    "vivokey-otp.cap": "A0000005272101014150455801",
    "YkHMACApplet.cap": "A000000527200101",
}


UNSUPPORTED_APPS = ["FIDO2.cap", "Satodime.cap", "keycard.cap"]

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
    release=None, verbose=False
) -> dict[str, str] or dict[str]:
    """
    Fetch a release from GitHub for the 'DangerousThings/flexsecure-applets' repo.
    Defaults to the latest release if no version is specified.

    Args:
        version (str, optional): The version or tag of the release to fetch. Defaults to None (latest release).

    Returns:
        dict[str, str]: A dictionary with the asset name as the key and download URL as the value.
    """
    if release:
        # If a specific version is requested, fetch that release by tag name
        url = (
            f"https://api.github.com/repos/{OWNER}/{REPO_NAME}/releases/tags/{release}"
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
            if (
                ".cap" in asset["name"] and asset["name"]
            ):  # Some releases have .jar files
                name = asset["name"]
                dl_url = asset["browser_download_url"]
                # Ensure the asset name is in the FLEXSECURE_AID_MAP if needed
                if name not in UNSUPPORTED_APPS:
                    results[name] = dl_url

        if verbose:
            return {"apps": results, "release": data["tag_name"]}

        return results

    except requests.exceptions.RequestException as e:
        print(f"Error fetching release: {e}")
        return {}


class FlexsecureAppletsPlugin(BaseAppletPlugin):
    """
    The single plugin for the entire 'flexsecure_applets' repository.
    """

    release = None

    def __init__(self):
        super().__init__()
        self._selected_cap = None
        self._override_instance = None
        self.auto_import_plugins("flexsecure_applets", override_map)

    @property
    def name(self) -> str:
        return "flexsecure_applets"

    def fetch_available_caps(self, release=None) -> dict[str, str]:
        res = fetch_flexsecure_release(release=release, verbose=True)

        self.release = res["release"]

        return res["apps"]

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

    def get_descriptions(self):
        with open(
            resource_path("repos/flexsecure_applets/applet_storage_by_release.json"),
            "r",
        ) as fh:
            storage = json.load(fh)
            fh.close()

        return {
            "javacard-memory.cap": f"""
                ## <a href="https://github.com/DangerousThings/javacard-memory">Memory Usage Reporting<a/>
                ### By: <a href="https://github.com/stargate01">StarGate01</a> from <a href="https://vivokey.com">VivoKey</a>
                ### Release: {self.release}
                
                This is used to determine memory usage on your smart card.
                <br />
                
            """,
            "keycard.cap": f"""
                ## Status.im Key Card
                This is three different applets in one cap file. Among them is a cold wallet.
                <br />
                
                - **Release**: {self.release}
            """,  # TODO: Add support for selecting apps in multi-app cap
            "openjavacard-ndef-full.cap": f"""
                ## <a href="https://github.com/OpenJavaCard/openjavacard-ndef">NDEF Container</a>
                ### By: <a href="https://github.com/OpenJavaCard">OpenJavaCard</a>
                ### Release: {self.release}
                {self.render_storage_req(storage, "openjavacard-ndef-full.cap")}
                
                This allows your smartcard to share data such as links.

                It is intended as a reusable library covering most usecases for NDEF on smartcards. There is support for emulating simple NDEF memory tags as well as for dynamic tags.
                <br />
                
            """,
            "SatoChip.cap": f"""
                ## <a href="https://github.com/Toporin/SatochipApplet">SatoChip</a>
                ### By <a href="https://satochip.io/">SatoChip.io</a>
                ### Release: {self.release}
                {self.render_storage_req(storage, "SatoChip.cap")}
                
                ### Introduction

                Satochip stands for **S**ecure **A**nonymous **T**rustless and **O**pen **Chip**. It is a javacard applet that can be used as a secure hardware wallet running for example on a [Yubikey Neo](https://store.yubico.com/store/catalog/product_info.php?ref=368&products_id=72&affiliate_banner_id=1). The Satochip applet has full BIP32/BIP39 supports.
                
                Using Satochip, an initial BIP32 seed is imported in the javacard and private keys are derived as requested by an external application. *Private keys are never exported outside of the secure chip*. To improve performances, the result of key derivation is cached in secure memory for future requests so that a specific derivation path is only computed once.
                
                The Satochip also supports the import of regular (non-BIP32 keys) such as vanity keys. Here again, private keys cannot be exported outside of the secure chip. Up to 16 regular keys can be imported on the chip. In any case, the private keys can be used to sign transactions and Bitcoin messages, if sufficient credentials are provided.
                
                Access to private keys (creation, derivation and signature) is enforced through the use of PIN code (from 4 to 16 chars).
                
                *This software is provided 'as-is', without any express or implied warranty. In no event will the authors be held liable for any damages arising from the use of this software.*
                
                Advantages:
                - Code is free and open source (no NDA required);
                - Code is easy to read and maintain (javacard is a subset of java);
                - Multiple form factor could be supported in addition to Yubikey (e.g sim cards);
                - Plug and play;
                - Smartcards have a long experience in dealing with security and physical security in particular;
                - Can be easily used or extended for other crypto-currencies;
                - A test package is run during build to ensure that critical functionalities are implemented correctly.
                
                Also, if used with a Yubikey:
                - Yubikey has minimal size and is practically indestructible;
                - The Yubico company is not going anywhere anytime soon;
                - Many promising functionalities: NFC, Yubikey OTP, U2F, ...;
                - Possibility to use the HMAC-SHA1 challenge-response of the Yubikey as second factor for additional security against malwares.
                
                Disadvantages:
                - Building the applet might be a bit tricky;
                - The software implementation of HMAC-SHA512 could have an potential impact on the physical security against side-channel attacks (for attackers with physical access to the chip).
                
                
            """,
            "Satodime.cap": f"""
                ## <a href="https://github.com/Toporin/Satodime-Applet">Satodime</a>
                ### By <a href="https://satochip.io/">SatoChip.io</a>
                {self.render_storage_req(storage, "Satodime.cap")}
                
                It is not compatible with Apex or flexSecure.Open source javacard applet implementing a bearer crypto card. The bearer chip card that allows you to spend crypto assets like a banknote. Safely pass it along multiple times,  unseal anytime with ease, thanks to cryptography. Trustless, easy to verify and completly secure.

                ### Introduction
                
                Satodime is a smartcard that stores cryptographic keypairs securely in a secure chip (also called Secure Element).
                Each keypair can be associated with a specific address on a blockchain.
                
                Each keypair is generated inside the secure chip and can be in any one of 3 states at any time:
                - uninitialized: the keypair has not been generated yet
                - sealed: the keypair has been generated securely inside the chip, only the public key is available
                - unsealed: the private key has been revealed
                
                Since the private key is generated inside the secure chip, a Satodime bearer can be certain that nobody (including himself) knows the private key until the key is unsealed.
                In effect, a Satodime allows to physically transfer cryptocurrencies such as Bitcoin from one person to another, without having to trust the bearer of the Satodime, AS LONG AS THE KEY IS IN THE SEALED STATE.
                
                Depending on the model, from 1 up to 3 keypairs can be stored simultaneously on a single Satodime.

            """,
            "SeedKeeper.cap": f"""
                ## <a href="https://github.com/Toporin/Seedkeeper-Applet">SeedKeeper</a>
                ### By <a href="https://satochip.io/">SatoChip.io</a>
                ### Release: {self.release}
                {self.render_storage_req(storage, "SeedKeeper.cap")}
                
                ### Introduction

                Traditionally, cryptocurrency users have used a simple pen and paper to keep a backup copy of their hardware wallet seed. 
                While this simple method works relatively well, it has also significant drawbacks: 
                * A piece of paper can be easily lost or destroyed
                * The seed is usually written in plaintext, since encryption is not practical (and how do you store the encryption key anyway?)
                
                A slightly more sophisticated way of securing your seed backup has been developed in the form of metal plates that are fire and water-proof.
                But the user is still left with the difficulty of protecting the seed from malicious unwanted eyes.
                And the challenge is only getting worse if you want to make multiple backups...
                
                With a SeedKeeper, Seeds are stored in the smartcard secure memory and can only be accessed by their legitimate owner using a short, easy-to-remember, secret PIN code. SeedKeeper is easy to use yet powerful; it is robust yet affordable; and last but not least, it is completely open-source. 
                SeedKeeper can be conveniently used in combination with a Satochip hardware wallet to serve as a secure backup. And you can use multiple SeedKeeper backups without compromising security!
            """,
            "SmartPGPApplet-default.cap": f"""
                ## <a href="https://github.com/github-af/SmartPGP">SmartPGP</a>
                ### By: <a href="https://github.com/github-af">github-af</a>
                ### Release: {self.release}
                {self.render_storage_req(storage, "SmartPGPApplet-default.cap")}
                
                Bring PGP/GPG operations such as encryption and signing to your smart card.
                
            """,
            "SmartPGPApplet-large.cap": f"""
                ## <a href="https://github.com/github-af/SmartPGP">SmartPGP - Large</a>
                ### By: <a href="https://github.com/github-af">github-af</a>
                ### Release: {self.release}
                {self.render_storage_req(storage, "SmartPGPApplet-large.cap")}
                
                Bring PGP/GPG operations such as encryption and signing to your smart card.
                <br />
                <br />
                **Note**: 'Large' allows the use of very large, inefficient RSA keys. If you don't
                    have existing keys meeting this criteria that you want to use, don't bother
                    with this version.
            """,
            "U2FApplet.cap": f"""
                ## <a href="https://github.com/darconeous/u2f-javacard">U2F Authenticator</a>
                ### By: <a href="https://github.com/darconeous">darconeous</a>
                ### Release: {self.release}
                {self.render_storage_req(storage, "U2FApplet.cap")}
                
                This is a fork of the [Ledger U2F Applet](https://github.com/LedgerHQ/ledger-u2f-javacard) that is focused on privacy and compatability. It has several unique features:

                * Still works with JC 3.0.1 cards.
                * Supports iOS via NFC, by [working around a bug in Apple's FIDO2 implementation](https://github.com/darconeous/u2f-javacard/commit/8b58c4cdcae295977306d895c7d5afd7c5628a22).
                * [Multiple counters (8)](https://github.com/darconeous/u2f-javacard/commit/554b0718cddf1eccc575bede16fb3f32cc44707e), which are assigned to registrations in a round-robin fashion.
                * [EEPROM wear-leveling for counters](https://github.com/darconeous/u2f-javacard/commit/c2f223d69300a4227d8865b72b3d72158191afd6)
                * [Supports "dont-enforce-user-presence-and-sign"](https://github.com/darconeous/u2f-javacard/commit/24b6f13f8c221771df6f087530574d222a71d6a1).
                
                This fork also [fixes some problems with Extended APDUs](https://github.com/darconeous/u2f-javacard/commit/7a7dcc7329405061bce430061584a20724ff1eda) that is [present in the upstream version](https://github.com/LedgerHQ/ledger-u2f-javacard/pull/13).
                
                If you want to just get a CAP file and install it, you can find it in the [releases section](https://github.com/darconeous/u2f-javacard/releases). Check the assets for the release, there should be a `U2FApplet.cap` and a `U2FApplet.cap.gpg`. The cap file is signed with [my public gpg key](https://keybase.io/darconeous).
                
                Once you have a CAP file, you can use [this script](https://gist.github.com/darconeous/adb1b2c4b15d3d8fbc72a5097270cdaf) to install using [GlobalPlatformPro](https://github.com/martinpaljak/GlobalPlatformPro).
                
                What follows below is from the original project README, with a few edits for things that have clearly changed.
                
                --------------------------------------
                
                
                ### Overview
                
                This applet is a Java Card implementation of the [FIDO Alliance U2F standard](https://fidoalliance.org/)
                
                It uses no proprietary vendor API and is freely available on [Ledger Unplugged](https://www.ledgerwallet.com/products/6-ledger-unplugged) and for a small fee on other Fidesmo devices through [Fidesmo store](http://www.fidesmo.com/apps/4f97a2e9)

            """,
            "FIDO2.cap": f"""
                ## <a href="https://github.com/BryanJacobs/FIDO2Applet">FIDO 2</a>
                ### By: <a href="https://github.com/BryanJacobs">Bryan Jacobs</a>
                ### Release: {self.release}
                {self.render_storage_req(storage, "FIDO2.cap")}
                
                ### Overview

                This repository contains sources for a feature-rich, FIDO2 CTAP2.1
                compatible applet targeting the Javacard Classic system, version 3.0.4. In a
                nutshell, this lets you take a smartcard, install an app onto it,
                and have it work as a FIDO2 authenticator device with a variety of
                features. You can generate and use OpenSSH `ecdsa-sk` type keys, including
                ones you carry with you on the key (`-O resident`). You can securely unlock
                a LUKS encrypted disk with `systemd-cryptenroll`. You can log in to a Linux
                system locally with [pam-u2f](https://github.com/Yubico/pam-u2f).
                
                100% of the FIDO2 CTAP2.1 spec is covered, with the exception of features
                that aren't physically on an ordinary smartcard, such as biometrics or
                other on-board user verification. The implementation in the default configuration
                passes the official FIDO certification test suite version 1.7.17 in
                "CTAP2.1 full feature profile" mode.
                
                In order to run this outside a simulator, you will need
                [a compatible smartcard](https://github.com/BryanJacobs/FIDO2Applet/blob/0194107d9648577379058b59843504924b546514/docs/requirements.md). Some smartcards which
                describe themselves as running Javacard 3.0.1 also work - see the
                detailed requirements.
                
                You might be interested in [reading about the security model](https://github.com/BryanJacobs/FIDO2Applet/blob/0194107d9648577379058b59843504924b546514/docs/security_model.md).
            """,
            "vivokey-otp.cap": f"""
                ## <a href="https://github.com/VivoKey/apex-totp">TOTP/HOTP Authenticator</a>
                ### By: <a href="https://github.com/stargate01">StarGate01</a> from <a href="https://vivokey.com">VivoKey</a>
                ### Release: {self.release}
                {self.render_storage_req(storage, "vivokey-otp.cap")}
                
                This allows you to generate TOTP codes on your smart card.
            """,
            "YkHMACApplet.cap": f"""
                ## <a href="https://github.com/DangerousThings/flexsecure-ykhmac">HMAC-SHA1 Challenge-Response</a>
                ### By: <a href="https://github.com/stargate01">StarGate01</a> from <a href="https://vivokey.com">VivoKey</a>
                ### Release: {self.release}
                {self.render_storage_req(storage, "YkHMACApplet.cap")}
                                
                This is a JavaCard applet that emulates the HMAC challenge-response functionality of the Yubikey NEO/4/5. It presents the same interface that a real Yubikey presents over CCID (i.e. this applet does not have any HID features).
                <br /><br />
                The goal is to be able to write applications that use the HMAC-SHA1 Challenge-Response mode of the Yubikey, and have a JavaCard with this applet be a drop-in replacement.
                <br /><br />
                Current status
                <br /><br />
                What works:
                
                - HMAC-SHA1 challenge response, in HMAC_LT64 mode
                - Setting configuration using CMD_SET_CONF_1, CMD_SET_CONF_2
                - Using the protection access code to prevent accidental slot overwrite

            """,
        }
