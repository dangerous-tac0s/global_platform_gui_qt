"""
Key configuration models for GlobalPlatform card key management.

Supports both single-key (SCP02/legacy) and separate-key (SCP03) modes.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class KeyType(Enum):
    """Supported key types based on algorithm and length."""

    DES = "DES"  # 8 bytes / 64 bits
    THREE_DES = "3DES"  # 16 bytes / 128 bits
    THREE_DES_192 = "3DES-192"  # 24 bytes / 192 bits
    AES_128 = "AES-128"  # 16 bytes / 128 bits
    AES_192 = "AES-192"  # 24 bytes / 192 bits
    AES_256 = "AES-256"  # 32 bytes / 256 bits


class KeyMode(Enum):
    """Key configuration mode."""

    SINGLE = "single"  # Single static key for all operations
    SEPARATE = "separate"  # Separate ENC/MAC/DEK keys (SCP03)


# Key lengths in bytes for each type
KEY_TYPE_LENGTHS = {
    KeyType.DES: 8,
    KeyType.THREE_DES: 16,
    KeyType.THREE_DES_192: 24,
    KeyType.AES_128: 16,
    KeyType.AES_192: 24,
    KeyType.AES_256: 32,
}

# Possible key types for each byte length (ambiguous lengths have multiple options)
LENGTH_TO_KEY_TYPES = {
    8: [KeyType.DES],
    16: [KeyType.THREE_DES, KeyType.AES_128],  # Ambiguous
    24: [KeyType.THREE_DES_192, KeyType.AES_192],  # Ambiguous
    32: [KeyType.AES_256],
}


def detect_key_type(key_hex: str, prefer_aes: bool = False) -> Optional[KeyType]:
    """
    Detect key type from hex string length.

    Args:
        key_hex: Hex string (spaces allowed)
        prefer_aes: For ambiguous lengths, prefer AES over 3DES

    Returns:
        KeyType or None if invalid length
    """
    clean = key_hex.replace(" ", "").upper()
    if len(clean) % 2 != 0:
        return None

    byte_len = len(clean) // 2
    types = LENGTH_TO_KEY_TYPES.get(byte_len)
    if not types:
        return None

    if len(types) == 1:
        return types[0]

    # Ambiguous - return based on preference
    if prefer_aes:
        return next((t for t in types if "AES" in t.value), types[0])
    return next((t for t in types if "DES" in t.value), types[0])


def is_ambiguous_length(byte_len: int) -> bool:
    """Check if the byte length is ambiguous (could be DES or AES)."""
    types = LENGTH_TO_KEY_TYPES.get(byte_len, [])
    return len(types) > 1


def get_type_display_name(key_type: KeyType) -> str:
    """Get human-readable display name for key type."""
    return key_type.value


def get_ambiguous_display(byte_len: int) -> str:
    """Get display string for ambiguous key lengths."""
    types = LENGTH_TO_KEY_TYPES.get(byte_len, [])
    if len(types) <= 1:
        return types[0].value if types else "Unknown"
    return " or ".join(t.value for t in types)


@dataclass
class KeyConfiguration:
    """
    Key configuration for a smart card.

    Supports two modes:
    - Single: One key used for all operations (SCP02 style)
    - Separate: Three separate keys for ENC/MAC/DEK (SCP03 style)
    """

    mode: KeyMode
    key_type: KeyType

    # Single mode
    static_key: Optional[str] = None

    # Separate mode (SCP03)
    enc_key: Optional[str] = None
    mac_key: Optional[str] = None
    dek_key: Optional[str] = None

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.mode == KeyMode.SINGLE:
            if not self.static_key:
                raise ValueError("Single mode requires static_key")
        elif self.mode == KeyMode.SEPARATE:
            if not all([self.enc_key, self.mac_key, self.dek_key]):
                raise ValueError("Separate mode requires enc_key, mac_key, and dek_key")

    def to_dict(self) -> dict:
        """Serialize to storage format."""
        result = {
            "mode": self.mode.value,
            "key_type": self.key_type.value,
        }
        if self.mode == KeyMode.SINGLE:
            result["static_key"] = self.static_key
        else:
            result["enc_key"] = self.enc_key
            result["mac_key"] = self.mac_key
            result["dek_key"] = self.dek_key
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "KeyConfiguration":
        """Deserialize from storage format."""
        mode = KeyMode(data["mode"])
        key_type = KeyType(data["key_type"])

        if mode == KeyMode.SINGLE:
            return cls(
                mode=mode,
                key_type=key_type,
                static_key=data.get("static_key"),
            )
        else:
            return cls(
                mode=mode,
                key_type=key_type,
                enc_key=data.get("enc_key"),
                mac_key=data.get("mac_key"),
                dek_key=data.get("dek_key"),
            )

    @classmethod
    def from_legacy_key(cls, key: str, prefer_aes: bool = False) -> "KeyConfiguration":
        """
        Create configuration from legacy single key string.

        Args:
            key: Hex key string
            prefer_aes: For ambiguous lengths, assume AES instead of 3DES
        """
        key_type = detect_key_type(key, prefer_aes=prefer_aes)
        if not key_type:
            # Default to 3DES for unknown lengths
            key_type = KeyType.THREE_DES

        return cls(
            mode=KeyMode.SINGLE,
            key_type=key_type,
            static_key=key.replace(" ", "").upper(),
        )

    def get_effective_key(self) -> str:
        """
        Get the primary key for authentication.

        For single mode, returns the static key.
        For separate mode, returns the ENC key (used as primary).
        """
        if self.mode == KeyMode.SINGLE:
            return self.static_key
        return self.enc_key

    def is_scp03(self) -> bool:
        """Check if this configuration uses SCP03 (separate keys)."""
        return self.mode == KeyMode.SEPARATE

    def uses_aes(self) -> bool:
        """Check if this configuration uses AES keys."""
        return "AES" in self.key_type.value
