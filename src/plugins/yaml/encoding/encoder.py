"""
Parameter Encoder

Encodes field values into installation parameters using various encoding methods:
- Template-based string substitution
- TLV (Tag-Length-Value) structure building
- Custom Python snippet execution
"""

import re
from typing import Any, Callable, Optional

from ..schema import (
    EncodingType,
    ParameterDefinition,
    TLVEntry,
)


class EncodingError(Exception):
    """Exception raised when parameter encoding fails."""
    pass


class TemplateProcessor:
    """
    Processes template strings with variable substitution.

    Supports:
    - Simple substitution: {field_id}
    - Hex encoding: {field_id_hex}
    - Length encoding: {field_id_length:02X}
    - Conditional sections: {?field_id}...{/field_id}
    """

    # Pattern for template variables
    VAR_PATTERN = re.compile(r'\{(\w+)(?::([^}]+))?\}')
    # Pattern for conditional sections
    COND_PATTERN = re.compile(r'\{\?(\w+)\}(.*?)\{/\1\}', re.DOTALL)

    @classmethod
    def process(
        cls,
        template: str,
        values: dict[str, Any],
        encoders: Optional[dict[str, Callable]] = None,
    ) -> str:
        """
        Process a template string with the given values.

        Args:
            template: Template string with {variable} placeholders
            values: Dictionary of field values
            encoders: Optional custom encoders for specific fields

        Returns:
            Processed string with values substituted
        """
        encoders = encoders or {}
        result = template

        # Process conditional sections first
        result = cls._process_conditionals(result, values)

        # Process variable substitutions
        result = cls._process_variables(result, values, encoders)

        return result

    @classmethod
    def _process_conditionals(cls, template: str, values: dict[str, Any]) -> str:
        """Process conditional sections {?field}...{/field}."""
        def replace_conditional(match):
            field_id = match.group(1)
            content = match.group(2)

            # Include content if field has a truthy value
            value = values.get(field_id)
            if value and value != "":
                return content
            return ""

        return cls.COND_PATTERN.sub(replace_conditional, template)

    # Pattern for combined length expressions like {field1+field2_length}
    COMBINED_LENGTH_PATTERN = re.compile(r'^(.+?)_length$')

    @classmethod
    def _process_variables(
        cls,
        template: str,
        values: dict[str, Any],
        encoders: dict[str, Callable],
    ) -> str:
        """Process variable substitutions."""
        def replace_var(match):
            var_name = match.group(1)
            format_spec = match.group(2)

            # First check if the exact variable name exists in values
            # This allows pre-computed values (like from dialog step) to override computation
            if var_name in values:
                value = values[var_name]
                if format_spec:
                    try:
                        return format(value, format_spec)
                    except (ValueError, TypeError):
                        return str(value)
                return str(value)

            # Check for special suffixes (computed if not in values)
            # _ascii_hex: Always encode as ASCII (for PINs, text fields)
            if var_name.endswith('_ascii_hex'):
                base_name = var_name[:-10]
                value = values.get(base_name, "")
                return cls._to_ascii_hex(value)

            # _hex: Auto-detect (existing hex stays as-is, text gets encoded)
            if var_name.endswith('_hex'):
                base_name = var_name[:-4]
                value = values.get(base_name, "")
                return cls._to_hex(value)

            # _ascii_length: Length of ASCII-encoded value (for PINs, text)
            if var_name.endswith('_ascii_length'):
                base_name = var_name[:-13]
                value = values.get(base_name, "")
                # ASCII length is just the string length
                length = len(str(value))
                if format_spec:
                    return format(length, format_spec)
                return str(length)

            if var_name.endswith('_length'):
                base_name = var_name[:-7]
                # Check for combined length (field1+field2_length)
                if '+' in base_name:
                    field_names = [f.strip() for f in base_name.split('+')]
                    total_length = 0
                    for field_name in field_names:
                        value = values.get(field_name, "")
                        total_length += len(cls._to_hex(value)) // 2
                    if format_spec:
                        return format(total_length, format_spec)
                    return str(total_length)
                else:
                    value = values.get(base_name, "")
                    length = len(cls._to_hex(value)) // 2
                    if format_spec:
                        return format(length, format_spec)
                    return str(length)

            # Check for custom encoder
            if var_name in encoders:
                value = values.get(var_name)
                return encoders[var_name](value)

            # Standard substitution
            value = values.get(var_name, "")

            if format_spec:
                try:
                    return format(value, format_spec)
                except (ValueError, TypeError):
                    return str(value)

            return str(value)

        return cls.VAR_PATTERN.sub(replace_var, template)

    @staticmethod
    def _to_hex(value: Any) -> str:
        """Convert a value to hex string (auto-detect)."""
        if isinstance(value, bytes):
            return value.hex().upper()
        elif isinstance(value, str):
            # If already hex, return as-is (uppercase)
            if re.match(r'^[0-9A-Fa-f]*$', value):
                return value.upper()
            # Otherwise encode as UTF-8 and convert to hex
            return value.encode('utf-8').hex().upper()
        elif isinstance(value, int):
            return format(value, 'X')
        else:
            return str(value).encode('utf-8').hex().upper()

    @staticmethod
    def _to_ascii_hex(value: Any) -> str:
        """Convert a value to hex by encoding as ASCII (for PINs, text)."""
        if isinstance(value, bytes):
            return value.hex().upper()
        elif isinstance(value, str):
            # Always encode as ASCII, even if it looks like hex
            return value.encode('ascii', errors='replace').hex().upper()
        elif isinstance(value, int):
            # Convert number to string first, then encode
            return str(value).encode('ascii').hex().upper()
        else:
            return str(value).encode('ascii', errors='replace').hex().upper()


class TLVBuilder:
    """
    Builds TLV (Tag-Length-Value) encoded byte strings.

    Supports:
    - Single-byte and multi-byte tags
    - Variable-length length fields
    - Nested TLV structures
    """

    @classmethod
    def build(
        cls,
        entries: list[TLVEntry],
        values: dict[str, Any],
    ) -> str:
        """
        Build a TLV-encoded hex string from entries.

        Args:
            entries: List of TLV entry definitions
            values: Field values for variable substitution

        Returns:
            Hex string of the complete TLV structure
        """
        result = ""

        for entry in entries:
            # Process the value template
            processed_value = TemplateProcessor.process(entry.value, values)

            # Skip empty values
            if not processed_value:
                continue

            # Clean the value (ensure it's hex)
            value_hex = cls._ensure_hex(processed_value)

            # Build the TLV entry
            tlv_entry = cls._build_entry(
                entry.tag,
                value_hex,
                entry.length_bytes,
            )
            result += tlv_entry

        return result

    @classmethod
    def _build_entry(cls, tag: str, value_hex: str, length_bytes: int) -> str:
        """Build a single TLV entry."""
        # Ensure tag is uppercase hex
        tag = tag.upper()

        # Calculate length (in bytes)
        value_length = len(value_hex) // 2

        # Encode length
        if length_bytes == 1:
            if value_length > 255:
                raise EncodingError(f"Value too long for 1-byte length: {value_length} bytes")
            length_hex = format(value_length, '02X')
        elif length_bytes == 2:
            if value_length > 65535:
                raise EncodingError(f"Value too long for 2-byte length: {value_length} bytes")
            length_hex = format(value_length, '04X')
        else:
            raise EncodingError(f"Unsupported length_bytes: {length_bytes}")

        return f"{tag}{length_hex}{value_hex}"

    @staticmethod
    def _ensure_hex(value: str) -> str:
        """Ensure a string is valid hex, removing any non-hex characters."""
        cleaned = re.sub(r'[^0-9A-Fa-f]', '', value)
        return cleaned.upper()

    @classmethod
    def build_single(
        cls,
        tag: str,
        value: bytes | str,
        length_bytes: int = 1,
    ) -> str:
        """
        Build a single TLV entry.

        Args:
            tag: Tag as hex string
            value: Value as bytes or hex string
            length_bytes: Number of bytes for length field

        Returns:
            Hex string of the TLV entry
        """
        if isinstance(value, bytes):
            value_hex = value.hex().upper()
        else:
            value_hex = cls._ensure_hex(value)

        return cls._build_entry(tag, value_hex, length_bytes)


class AIDBuilder:
    """
    Builds Application Identifiers (AIDs) from dynamic construction rules.

    Supports:
    - Static base AID
    - Dynamic segments from field values
    - Default segment values
    """

    @classmethod
    def build(
        cls,
        base: str,
        segments: list[dict],
        values: dict[str, Any],
    ) -> str:
        """
        Build a complete AID from base and segments.

        Args:
            base: Base AID prefix (hex string)
            segments: List of segment definitions
            values: Field values for dynamic segments

        Returns:
            Complete AID as hex string
        """
        result = base.upper()

        for segment in segments:
            segment_value = cls._get_segment_value(segment, values)
            result += segment_value

        # Validate AID length (5-16 bytes)
        aid_bytes = len(result) // 2
        if aid_bytes < 5 or aid_bytes > 16:
            raise EncodingError(
                f"Invalid AID length: {aid_bytes} bytes. "
                "AIDs must be 5-16 bytes."
            )

        return result

    @classmethod
    def _get_segment_value(cls, segment: dict, values: dict[str, Any]) -> str:
        """Get the value for a single segment."""
        name = segment.get("name", "")
        length = segment.get("length", 0)
        source = segment.get("source")
        default = segment.get("default", "")

        # Determine the value
        if source:
            # Parse source reference (e.g., "field:manufacturer_id")
            if source.startswith("field:"):
                field_id = source[6:]
                value = values.get(field_id, default)
            else:
                value = default
        else:
            value = default

        # Ensure value is hex
        if isinstance(value, int):
            value = format(value, 'X')
        elif isinstance(value, bytes):
            value = value.hex()

        value = str(value).upper()
        value = re.sub(r'[^0-9A-Fa-f]', '', value)

        # Pad or truncate to required length
        required_chars = length * 2
        if len(value) < required_chars:
            value = value.zfill(required_chars)
        elif len(value) > required_chars:
            value = value[:required_chars]

        return value


class ParameterEncoder:
    """
    Main encoder that combines template, TLV, and custom encoding.
    """

    def __init__(self, param_def: Optional[ParameterDefinition] = None):
        """
        Initialize the encoder.

        Args:
            param_def: Parameter definition from YAML schema
        """
        self._param_def = param_def

    def encode(self, values: dict[str, Any]) -> dict[str, Any]:
        """
        Encode field values into installation parameters.

        Args:
            values: Dictionary of field values

        Returns:
            Dictionary with:
                - param_string: The encoded parameter string
                - create_aid: Optional AID for --create flag
        """
        if not self._param_def:
            return {"param_string": "", "create_aid": None}

        result = {
            "param_string": "",
            "create_aid": self._param_def.create_aid,
        }

        encoding_type = self._param_def.encoding

        if encoding_type == EncodingType.NONE:
            pass  # No parameters

        elif encoding_type == EncodingType.TEMPLATE:
            if self._param_def.template:
                result["param_string"] = TemplateProcessor.process(
                    self._param_def.template,
                    values,
                )

        elif encoding_type == EncodingType.TLV:
            if self._param_def.tlv_structure:
                result["param_string"] = TLVBuilder.build(
                    self._param_def.tlv_structure,
                    values,
                )

        elif encoding_type == EncodingType.CUSTOM:
            if self._param_def.builder:
                result["param_string"] = self._execute_custom_builder(
                    self._param_def.builder,
                    values,
                )

        return result

    def _execute_custom_builder(self, builder_code: str, values: dict[str, Any]) -> str:
        """
        Execute a custom builder script.

        Args:
            builder_code: Python code snippet
            values: Field values

        Returns:
            Encoded parameter string
        """
        # Create a restricted execution environment
        local_vars = {
            "field_values": values,
            "result": "",
        }

        # Safe built-ins
        safe_builtins = {
            "len": len,
            "str": str,
            "int": int,
            "hex": hex,
            "format": format,
            "bytes": bytes,
            "bytearray": bytearray,
            "range": range,
            "enumerate": enumerate,
            "zip": zip,
            "map": map,
            "filter": filter,
            "list": list,
            "dict": dict,
            "tuple": tuple,
            "set": set,
            "True": True,
            "False": False,
            "None": None,
        }

        global_vars = {"__builtins__": safe_builtins}

        try:
            exec(builder_code, global_vars, local_vars)
            return local_vars.get("result", "")
        except Exception as e:
            raise EncodingError(f"Custom builder failed: {e}")

    def build_aid(
        self,
        aid_construction: dict,
        values: dict[str, Any],
    ) -> str:
        """
        Build a dynamic AID.

        Args:
            aid_construction: AID construction definition
            values: Field values

        Returns:
            Complete AID as hex string
        """
        return AIDBuilder.build(
            aid_construction.get("base", ""),
            aid_construction.get("segments", []),
            values,
        )
