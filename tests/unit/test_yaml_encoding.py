"""
Unit tests for YAML Plugin Parameter Encoding

Tests the TemplateProcessor, TLVBuilder, AIDBuilder, and ParameterEncoder.
"""

import pytest

from src.plugins.yaml.schema import (
    EncodingType,
    ParameterDefinition,
    TLVEntry,
)
from src.plugins.yaml.encoding.encoder import (
    EncodingError,
    TemplateProcessor,
    TLVBuilder,
    AIDBuilder,
    ParameterEncoder,
)


class TestTemplateProcessor:
    """Tests for TemplateProcessor class."""

    def test_simple_substitution(self):
        """Test simple variable substitution."""
        template = "Hello {name}!"
        values = {"name": "World"}

        result = TemplateProcessor.process(template, values)
        assert result == "Hello World!"

    def test_multiple_variables(self):
        """Test multiple variable substitutions."""
        template = "{tag}{value}"
        values = {"tag": "81", "value": "AABB"}

        result = TemplateProcessor.process(template, values)
        assert result == "81AABB"

    def test_hex_suffix(self):
        """Test _hex suffix for hex encoding."""
        template = "{data_hex}"
        values = {"data": "Hello"}

        result = TemplateProcessor.process(template, values)
        assert result == "48656C6C6F"  # "Hello" in hex

    def test_hex_suffix_passthrough(self):
        """Test _hex suffix with already hex value."""
        template = "{data_hex}"
        values = {"data": "DEADBEEF"}

        result = TemplateProcessor.process(template, values)
        assert result == "DEADBEEF"

    def test_length_suffix(self):
        """Test _length suffix for length encoding."""
        template = "{data_length:02X}"
        values = {"data": "AABBCCDD"}  # 4 bytes

        result = TemplateProcessor.process(template, values)
        assert result == "04"

    def test_format_spec(self):
        """Test format specifier."""
        template = "{count:04X}"
        values = {"count": 255}

        result = TemplateProcessor.process(template, values)
        assert result == "00FF"

    def test_conditional_included(self):
        """Test conditional section when value is truthy."""
        template = "PREFIX{?optional}OPTIONAL{/optional}SUFFIX"
        values = {"optional": "yes"}

        result = TemplateProcessor.process(template, values)
        assert result == "PREFIXOPTIONALSUFFIX"

    def test_conditional_excluded(self):
        """Test conditional section when value is falsy."""
        template = "PREFIX{?optional}OPTIONAL{/optional}SUFFIX"
        values = {"optional": ""}

        result = TemplateProcessor.process(template, values)
        assert result == "PREFIXSUFFIX"

    def test_conditional_with_variables(self):
        """Test conditional section containing variables."""
        template = "BASE{?extra}_{extra_value}{/extra}"
        values = {"extra": "yes", "extra_value": "DATA"}

        result = TemplateProcessor.process(template, values)
        assert result == "BASE_DATA"

    def test_missing_variable(self):
        """Test handling of missing variables."""
        template = "{present}{missing}"
        values = {"present": "A"}

        result = TemplateProcessor.process(template, values)
        assert result == "A"

    def test_bytes_to_hex(self):
        """Test converting bytes to hex."""
        template = "{data_hex}"
        values = {"data": b'\xDE\xAD\xBE\xEF'}

        result = TemplateProcessor.process(template, values)
        assert result == "DEADBEEF"


class TestTLVBuilder:
    """Tests for TLVBuilder class."""

    def test_single_entry(self):
        """Test building a single TLV entry."""
        entries = [
            TLVEntry(tag="81", value="{data}", length_bytes=1)
        ]
        values = {"data": "AABB"}

        result = TLVBuilder.build(entries, values)
        assert result == "8102AABB"  # tag=81, length=02, value=AABB

    def test_multiple_entries(self):
        """Test building multiple TLV entries."""
        entries = [
            TLVEntry(tag="81", value="{perm}", length_bytes=1),
            TLVEntry(tag="82", value="{size}", length_bytes=2),
        ]
        values = {"perm": "00FF", "size": "1000"}

        result = TLVBuilder.build(entries, values)
        # 81 02 00FF (perm: 2 bytes) + 82 0002 1000 (size: 2 bytes)
        assert result == "810200FF8200021000"

    def test_empty_value_skipped(self):
        """Test that empty values are skipped."""
        entries = [
            TLVEntry(tag="81", value="{data1}", length_bytes=1),
            TLVEntry(tag="82", value="{data2}", length_bytes=1),
        ]
        values = {"data1": "AA", "data2": ""}

        result = TLVBuilder.build(entries, values)
        assert result == "8101AA"  # Only first entry

    def test_two_byte_length(self):
        """Test 2-byte length encoding."""
        entries = [
            TLVEntry(tag="83", value="{data}", length_bytes=2)
        ]
        values = {"data": "AB" * 256}  # 256 bytes

        result = TLVBuilder.build(entries, values)
        assert result.startswith("830100")  # tag=83, length=0100 (256)

    def test_build_single(self):
        """Test building a single TLV entry directly."""
        result = TLVBuilder.build_single("80", "DEADBEEF", length_bytes=1)
        assert result == "8004DEADBEEF"

    def test_build_single_from_bytes(self):
        """Test building TLV from bytes."""
        result = TLVBuilder.build_single("80", b'\xAB\xCD', length_bytes=1)
        assert result == "8002ABCD"


class TestAIDBuilder:
    """Tests for AIDBuilder class."""

    def test_static_aid(self):
        """Test building with static base only."""
        result = AIDBuilder.build(
            base="D276000124010304",
            segments=[],
            values={},
        )
        assert result == "D276000124010304"

    def test_dynamic_segments(self):
        """Test building with dynamic segments."""
        result = AIDBuilder.build(
            base="D276000124010304",
            segments=[
                {"name": "manufacturer", "length": 2, "source": "field:mfr_id"},
                {"name": "serial", "length": 4, "source": "field:serial"},
            ],
            values={"mfr_id": "000A", "serial": "00000001"},
        )
        assert result == "D276000124010304000A00000001"

    def test_default_values(self):
        """Test using default values for segments."""
        result = AIDBuilder.build(
            base="D276000124010304",
            segments=[
                {"name": "manufacturer", "length": 2, "default": "FFFF"},
                {"name": "reserved", "length": 2, "default": "0000"},
            ],
            values={},
        )
        assert result == "D276000124010304FFFF0000"

    def test_padding_short_values(self):
        """Test padding short values to required length."""
        result = AIDBuilder.build(
            base="D2760001",
            segments=[
                {"name": "version", "length": 2, "source": "field:ver"},
            ],
            values={"ver": "1"},  # Only 1 char, needs padding to 4
        )
        # "1" becomes "0001" (4 hex chars = 2 bytes)
        assert result == "D27600010001"

    def test_truncating_long_values(self):
        """Test truncating long values to required length."""
        result = AIDBuilder.build(
            base="D2760001",
            segments=[
                {"name": "data", "length": 2, "source": "field:data"},
            ],
            values={"data": "AABBCCDD"},  # 4 bytes, needs truncation to 2
        )
        assert result == "D2760001AABB"

    def test_invalid_aid_length_short(self):
        """Test that short AIDs raise error."""
        with pytest.raises(EncodingError) as exc_info:
            AIDBuilder.build(
                base="D276",  # Only 2 bytes
                segments=[],
                values={},
            )
        assert "Invalid AID length" in str(exc_info.value)

    def test_invalid_aid_length_long(self):
        """Test that long AIDs raise error."""
        with pytest.raises(EncodingError) as exc_info:
            AIDBuilder.build(
                base="D276000124010304",  # 8 bytes
                segments=[
                    {"name": "extra", "length": 10, "default": "00" * 10},  # 10 more bytes = 18 total
                ],
                values={},
            )
        assert "Invalid AID length" in str(exc_info.value)


class TestParameterEncoder:
    """Tests for ParameterEncoder class."""

    def test_no_encoding(self):
        """Test with no encoding."""
        param_def = ParameterDefinition(encoding=EncodingType.NONE)
        encoder = ParameterEncoder(param_def)

        result = encoder.encode({"field": "value"})
        assert result["param_string"] == ""

    def test_template_encoding(self):
        """Test template-based encoding."""
        param_def = ParameterDefinition(
            encoding=EncodingType.TEMPLATE,
            template="8102{read_perm}{write_perm}",
        )
        encoder = ParameterEncoder(param_def)

        result = encoder.encode({"read_perm": "00", "write_perm": "FF"})
        assert result["param_string"] == "810200FF"

    def test_tlv_encoding(self):
        """Test TLV-based encoding."""
        param_def = ParameterDefinition(
            encoding=EncodingType.TLV,
            tlv_structure=[
                TLVEntry(tag="81", value="{permissions}", length_bytes=1),
                TLVEntry(tag="82", value="{size}", length_bytes=2),
            ],
        )
        encoder = ParameterEncoder(param_def)

        result = encoder.encode({"permissions": "00FF", "size": "1000"})
        # 81 02 00FF + 82 0002 1000
        assert "8102" in result["param_string"]
        assert "00FF" in result["param_string"]

    def test_custom_encoding(self):
        """Test custom builder encoding."""
        param_def = ParameterDefinition(
            encoding=EncodingType.CUSTOM,
            builder="""
parts = []
if field_values.get("enable"):
    parts.append("01")
else:
    parts.append("00")
parts.append(field_values.get("data", ""))
result = "".join(parts)
""",
        )
        encoder = ParameterEncoder(param_def)

        result = encoder.encode({"enable": True, "data": "AABB"})
        assert result["param_string"] == "01AABB"

    def test_create_aid(self):
        """Test that create_aid is passed through."""
        param_def = ParameterDefinition(
            encoding=EncodingType.TEMPLATE,
            template="{data}",
            create_aid="D276000124010304",
        )
        encoder = ParameterEncoder(param_def)

        result = encoder.encode({"data": "TEST"})
        assert result["create_aid"] == "D276000124010304"

    def test_none_param_def(self):
        """Test with no parameter definition."""
        encoder = ParameterEncoder(None)

        result = encoder.encode({"field": "value"})
        assert result["param_string"] == ""
        assert result["create_aid"] is None

    def test_build_aid(self):
        """Test building dynamic AID."""
        encoder = ParameterEncoder(None)

        aid_construction = {
            "base": "D276000124010304",
            "segments": [
                {"name": "mfr", "length": 2, "source": "field:manufacturer"},
                {"name": "serial", "length": 4, "source": "field:serial"},
            ],
        }

        result = encoder.build_aid(
            aid_construction,
            {"manufacturer": "000A", "serial": "00000001"},
        )
        assert result == "D276000124010304000A00000001"


class TestComplexEncoding:
    """Tests for complex encoding scenarios."""

    def test_ndef_style_encoding(self):
        """Test NDEF-style parameter encoding."""
        # Simulating NDEF container configuration
        param_def = ParameterDefinition(
            encoding=EncodingType.TEMPLATE,
            template="{?data}80{data_length:02X}{data_hex}{/data}8102{read_perm}{write_perm}{?size}8202{size}{/size}",
        )
        encoder = ParameterEncoder(param_def)

        result = encoder.encode({
            "data": "AB",
            "read_perm": "00",
            "write_perm": "00",
            "size": "1000",
        })

        # Should include: data record + permissions + size
        assert "8001AB" in result["param_string"]  # data
        assert "81020000" in result["param_string"]  # permissions
        assert "82021000" in result["param_string"]  # size

    def test_smartpgp_aid_construction(self):
        """Test SmartPGP-style AID construction."""
        result = AIDBuilder.build(
            base="D276000124010304",  # OpenPGP AID prefix
            segments=[
                {"name": "manufacturer", "length": 2, "source": "field:mfr"},
                {"name": "serial", "length": 4, "source": "field:serial"},
                {"name": "reserved", "length": 2, "default": "0000"},
            ],
            values={
                "mfr": "000A",  # VivoKey manufacturer ID
                "serial": "00000001",
            },
        )

        # Full AID: D276000124010304 + 000A + 00000001 + 0000
        assert result == "D276000124010304000A000000010000"
        assert len(result) == 32  # 16 bytes = 32 hex chars
