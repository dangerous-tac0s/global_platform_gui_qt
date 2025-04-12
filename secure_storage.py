import ctypes
import os
import json
import base64
import subprocess

import keyring
import gnupg
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from secrets import token_bytes


class SecureStorage:

    def __init__(
        self,
        path: str,
        # gpg_home=os.getcwd(),
        service_name="SecureStorage",
    ):
        self.__path = path
        self.__data = None
        self.__aes_key = None
        self.__method = None
        self.__key_id = None
        self.__gpg = gnupg.GPG()
        self.__wrapped_key_b64 = None
        self.service_name = service_name
        self.__meta: None | dict = None
        self.__persist_key = False

    @property
    def meta(self):
        return self.__meta

    def select_key(self) -> bytes:
        if self.__method == "keyring":
            b64key = keyring.get_password(self.service_name, self.__key_id)
            if not b64key:
                raise RuntimeError("Key not found in keyring")
            return base64.b64decode(b64key)

        elif self.__method == "gpg":
            if not self.__wrapped_key_b64:
                raise RuntimeError("No wrapped_key available for GPG")
            wrapped = base64.b64decode(self.__wrapped_key_b64)
            try:
                result = gpg_decrypt(wrapped)
                return result
            except ValueError as e:
                raise RuntimeError(f"GPG decryption failed: {e}")

        else:
            raise ValueError(f"Unsupported key selection method: {self.__method}")

    def initialize(self, method, key_id: str = None, initial_data={}):
        if self.meta:
            self.__method = method["keywrapping"]["method"]
        else:
            self.__method = method
            self.__key_id = key_id
            self.__aes_key = token_bytes(32)

        if method == "keyring":
            keyring.set_password(
                self.service_name, key_id, base64.b64encode(self.__aes_key).decode()
            )

        elif method == "gpg":
            if not key_id:
                raise ValueError("GPG method requires key_id.")

            result = self.__gpg.encrypt(self.__aes_key, recipients=key_id, armor=True)

            self.__wrapped_key_b64 = base64.b64encode(result.data).decode()

        else:
            raise ValueError("Unsupported encryption method")

        self.__data = initial_data

        self.save()
        self.load()

    def change_method(self, new_method: str, new_key_id: str):
        if self.__data is None:
            raise RuntimeError("Load or set data before changing encryption method.")

        _zero_bytes(self.__aes_key)
        self.__aes_key = None  # Clear old key reference
        self.initialize(new_method, new_key_id)

    def load(self, retry=False):
        if not os.path.exists(self.__path):
            raise FileNotFoundError(f"Unable to find {self.__path}")

        with open(self.__path, "rb") as f:
            obj = json.load(f)

        meta = obj["key_wrapping"]
        self.__method = meta["method"]
        self.__key_id = meta["key_id"]

        if self.__method == "keyring":
            b64key = keyring.get_password(self.service_name, self.__key_id)
            if not b64key:
                raise RuntimeError("Key not found in keyring")
            self.__aes_key = base64.b64decode(b64key)

        elif self.__method == "gpg":
            self.__wrapped_key_b64 = meta["wrapped_key_b64"]
            wrapped = base64.b64decode(meta["wrapped_key_b64"])
            try:
                result = gpg_decrypt(wrapped)
            except Exception as e:
                if not retry:
                    self.load(retry=True)
                else:
                    raise RuntimeError(e)

            self.__aes_key = result

        else:
            raise ValueError("Unsupported encryption method")

        enc = obj["encryption"]
        iv = base64.b64decode(enc["iv"])
        tag = base64.b64decode(enc["tag"])
        ciphertext = base64.b64decode(obj["payload"])
        aesgcm = AESGCM(self.__aes_key)
        self.__data = json.loads(aesgcm.decrypt(iv, ciphertext + tag, None))

        _zero_bytes(self.__aes_key)
        self.__aes_key = None

    def save(self):
        if not self.__aes_key:
            self.__aes_key = self.select_key()

        if self.__data is None or self.__aes_key is None:
            raise RuntimeError("No data or AES key initialized")

        aesgcm = AESGCM(self.__aes_key)
        iv = token_bytes(12)
        json_bytes = json.dumps(self.__data).encode()
        encrypted = aesgcm.encrypt(iv, json_bytes, None)
        _zero_bytes(self.__aes_key)
        self.__aes_key = None

        tag = encrypted[-16:]
        ciphertext = encrypted[:-16]

        metadata = {
            "version": 1,
            "encryption": {
                "cipher": "AES-256-GCM",
                "iv": base64.b64encode(iv).decode(),
                "tag": base64.b64encode(tag).decode(),
            },
            "key_wrapping": {
                "method": self.__method,
                "key_id": self.__key_id,
            },
        }

        if self.__method == "gpg":
            metadata["key_wrapping"]["wrapped_key_b64"] = self.__wrapped_key_b64

        with open(self.__path, "w") as f:
            json.dump(
                {**metadata, "payload": base64.b64encode(ciphertext).decode()},
                f,
                indent=2,
            )

    def set_data(self, data: dict):
        self.__data = data

    def get_data(self) -> dict:
        return self.__data

    def gpg_unwrap_key(self):
        pass


def _zero_bytes(buf: bytes):
    ctypes.memset(
        ctypes.addressof(ctypes.create_string_buffer(buf, len(buf))), 0, len(buf)
    )


def gpg_decrypt(ciphertext: bytes) -> bytes:
    """
    Pin entry doesn't work with the library *sigh*
    """

    p = subprocess.run(["gpg", "--decrypt"], input=ciphertext, capture_output=True)

    if p.returncode != 0:
        raise RuntimeError(f"GPG decryption failed: {p.stderr.decode()}")

    return p.stdout
