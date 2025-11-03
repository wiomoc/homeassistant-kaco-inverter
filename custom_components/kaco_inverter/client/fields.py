"""Definition of the fields returned in the responses by the inverter."""

import abc
import typing
from dataclasses import dataclass

import crc

from . import ProtocolException


class _Field(typing.Protocol):
    def read(
        self,
        frame: bytes,
        position: int,
        dest_dict: dict[str, typing.Any],
        annotate: bool,
    ) -> int:
        """Read the field based on the given frame at the given position.

        Args:
            frame: Frame to read from
            position: Start position to read at
            dest_dict: Dict to write the read and parsed value to
            annotate (bool): True if the read and parsed value should be wrapped
                into an AnnotatedValue object

        Returns:
            int: Cursor position after reading the field
        """


def expect_min_remaining_frame_length(
    frame: bytes, position: int, min_remaining_length: int
) -> None:
    """Validiate the frame to have a minimum of remaining bytes."""
    if len(frame) < (position + min_remaining_length):
        raise ProtocolException("Unexpected end-of-frame")


def _expect_char(frame: bytes, position: int, char: str) -> None:
    assert len(char) == 1
    if frame[position] != ord(char):
        raise ProtocolException(
            f"Expected '{char}', got {frame[position : position + 1]!r}"
        )


@dataclass
class AnnotatedValue[T]:
    """Representation of a value with a quantity and a human-readable description."""

    value: T
    quantity: str
    description: str


class _ValueField[T](_Field, abc.ABC):
    _name: str
    _length: int | None
    _quantity: str | None
    _description: str | None

    def __init__(
        self,
        name: str,
        length: int | None = None,
        /,
        quantity: str | None = None,
        description: str | None = None,
    ):
        super().__init__()
        self._name = name
        self._length = length
        self._quantity = quantity
        self._description = description

    def read(
        self,
        frame: bytes,
        position: int,
        dest_dict: dict[str, typing.Any],
        annotate: bool = False,
    ) -> int:
        start_pos = position + 1
        if self._length is None:
            expect_min_remaining_frame_length(frame, position, 2)
            _expect_char(frame, position, " ")
            found_non_space = False
            for end_pos in range(position, len(frame)):
                if frame[end_pos] == ord(" "):
                    if found_non_space:
                        break
                else:
                    found_non_space = True
            else:
                raise ProtocolException("Expected ' ', got end-of-frame")
        else:
            expect_min_remaining_frame_length(frame, position, self._length + 1)
            _expect_char(frame, position, " ")
            end_pos = start_pos + self._length

        field_value_bytes = frame[start_pos:end_pos]
        field_value = self.parse(field_value_bytes)
        if annotate and self._description and self._quantity:
            dest_dict[self._name] = AnnotatedValue(
                value=field_value,
                quantity=self._quantity,
                description=self._description,
            )
        else:
            dest_dict[self._name] = field_value
        return end_pos

    @abc.abstractmethod
    def parse(self, field_value_bytes: bytes) -> T:
        """Parse the given raw field value bytes to a native value."""


class _StringField(_ValueField[str]):
    """Represents a floating-point number field (' abcd')."""

    def parse(self, field_value_bytes: bytes) -> str:
        try:
            return field_value_bytes.lstrip(b"\0").decode("ASCII").lstrip()
        except UnicodeDecodeError as e:
            raise ProtocolException(
                f"Expected ASCII characters, got {field_value_bytes!r}"
            ) from e


class _IntField(_ValueField[int]):
    """Represents a floating-point number field ('1234')."""

    def parse(self, field_value_bytes: bytes) -> int:
        try:
            field_value_string = field_value_bytes.decode("ASCII").lstrip()
            return int(field_value_string)
        except (UnicodeDecodeError, ValueError) as e:
            raise ProtocolException(
                f"Expected integer, got {field_value_bytes!r}"
            ) from e


class _FloatField(_ValueField[float]):
    """Represents a floating-point number field ('123.45')."""

    _precision: int | None

    def __init__(
        self,
        /,
        *args,
        precision: int | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._precision = precision

    def parse(self, field_value_bytes: bytes) -> float:
        try:
            field_value_string = field_value_bytes.decode("ASCII").lstrip()
            if self._precision is not None and (
                len(field_value_string) < (self._precision + 2)
                or field_value_string[-1 - self._precision] != "."
            ):
                raise ProtocolException(
                    f"Expected {self._precision} decimal places in field {self._name}"
                )
            return float(field_value_string)
        except (UnicodeDecodeError, ValueError) as e:
            raise ProtocolException(f"Expected float, got {field_value_bytes!r}") from e


class _CosPhiField(_FloatField):
    def parse(self, field_value_bytes: bytes) -> float:
        if field_value_bytes[-1:] not in {b"c", b"i", b"o"}:
            raise ProtocolException(
                f"Expected c, i or o, got {field_value_bytes[-1:]!r}"
            )
        return super().parse(field_value_bytes[:-1])


class _DurationField(_ValueField[int]):
    """Represents a duration field ('hhhhhh:mm')."""

    def parse(self, field_value_bytes: bytes) -> int:
        _expect_char(field_value_bytes, -3, ":")
        try:
            field_value_string = field_value_bytes.decode("ASCII").lstrip()
            hours = int(field_value_string[:-3])
            minutes = int(field_value_string[-2:])
            return 60 * hours + minutes
        except (UnicodeDecodeError, ValueError) as e:
            raise ProtocolException(
                f"Expected duration, got '{field_value_bytes!r}'"
            ) from e


class LegacyChecksumField(_Field):
    """Represents a one-byte checksum used in the legacy protocol."""

    def read(self, frame: bytes, position: int, *_args, **_kwargs) -> int:
        """Read the field and validate the checksum."""
        expect_min_remaining_frame_length(frame, position, 2)
        _expect_char(frame, position, " ")
        excepted_checksum = frame[position + 1]
        relevant_payload = frame[1 : position + 1]
        actual_checksum = sum(relevant_payload) & 0xFF
        if actual_checksum != excepted_checksum:
            raise ProtocolException(
                f"Expected checksum {excepted_checksum}, got {actual_checksum}"
            )
        return position + 2


class _StartField(_Field):
    r"""Represents the start of a frame('\n*<ADR><COMMAND> ')."""

    def read(self, frame: bytes, position: int, *_args, **_kwargs) -> int:
        length = 5
        assert position == 0
        expect_min_remaining_frame_length(frame, position, length)
        _expect_char(frame, position, "\n")
        _expect_char(frame, position + 1, "*")
        try:
            frame[2:position].decode("ASCII")
        except (UnicodeDecodeError, ValueError) as e:
            raise ProtocolException(
                f"Expected address and command, got {frame[2:position]!r}"
            ) from e

        return position + length


class _LegacyStopField(_Field):
    r"""Represents the end of a frame ('\r') ."""

    def read(self, frame: bytes, position: int, *_args, **_kwargs) -> int:
        expect_min_remaining_frame_length(frame, position, 1)
        _expect_char(frame, position, "\r")
        if len(frame) > (position + 1):
            raise ProtocolException("Expected end-of-frame")
        return position + 1


_crc_calculator = crc.Calculator(crc.Crc16.X25.value)


class _CrcAndStopField(_Field):
    """Represents a CRC16 checksum used in the generic protocol."""

    def read(self, frame: bytes, position: int, *_args, **_kwargs):
        length = 6
        expect_min_remaining_frame_length(frame, position, length)
        _expect_char(frame, position, " ")
        crc_hex = frame[position + 1 : position + 5]
        try:
            expected_crc = int(crc_hex.decode("ASCII"), 16)
        except (UnicodeDecodeError, ValueError) as e:
            raise ProtocolException(f"Expected hex, got {crc_hex!r}") from e

        crc_dc_bytes = frame[1 : position + 1]
        actual_crc = _crc_calculator.checksum(crc_dc_bytes)
        if actual_crc != expected_crc:
            raise ProtocolException(
                f"Expected CRC {expected_crc:02X}, got {actual_crc:02X}"
            )

        _expect_char(frame, position + 5, "\r")

        if len(frame) > position + length:
            raise ProtocolException("Expected end-of-frame")


# 2 KACO Standard "legacy" protocol
FIELDS_SERIES_00_02 = (
    _StartField(),
    _IntField("status", 3),
    _FloatField(
        "dc_voltage", 5, precision=1, quantity="V", description="Generator Voltage"
    ),
    _FloatField(
        "dc_current", 5, precision=2, quantity="A", description="Generator Current"
    ),
    _IntField("dc_power", 5, quantity="W", description="Generator Power"),
    _FloatField("ac_voltage", 5, precision=1, quantity="V", description="Grid Voltage"),
    _FloatField(
        "ac_current",
        5,
        precision=2,
        quantity="A",
        description="Grid- / Grid-feeding Current",
    ),
    _IntField("ac_power", 5, quantity="W", description="Delivered (fed-in) Power"),
    _IntField("device_temperature", 3, quantity="°C", description="Device Temperature"),
    _IntField("daily_yield", 6, quantity="Wh", description="Daily Yield"),
    LegacyChecksumField(),
    _StringField("inverter_type", 6),
    _LegacyStopField(),
)

FIELDS_SERIES_000XI = (
    _StartField(),
    _IntField("status", 3),
    _FloatField(
        "dc_voltage", 5, precision=1, quantity="V", description="Generator Voltage"
    ),
    _FloatField(
        "dc_current", 5, precision=2, quantity="A", description="Generator Current"
    ),
    _IntField("dc_power", 6, quantity="W", description="Generator Power"),
    _FloatField("ac_voltage", 5, precision=1, quantity="V", description="Grid Voltage"),
    _FloatField(
        "ac_current",
        5,
        precision=2,
        quantity="A",
        description="Grid- / Grid-feeding Current",
    ),
    _IntField("ac_power", 6, quantity="W", description="Delivered (fed-in) Power"),
    _IntField("device_temperature", 2, quantity="°C", description="Device Temperature"),
    _IntField("daily_yield", 6, quantity="Wh", description="Daily Yield"),
    LegacyChecksumField(),
    _StringField("inverter_type", 4),
    _LegacyStopField(),
)

FIELDS_SERIES_XP = (
    _StartField(),
    _IntField("status", 3),
    _FloatField(
        "dc_voltage", 5, precision=1, quantity="V", description="Generator Voltage"
    ),
    _FloatField(
        "dc_current", 6, precision=2, quantity="A", description="Generator Current"
    ),
    _IntField("dc_power", 6, quantity="W", description="Generator Power"),
    _FloatField("ac_voltage", 5, precision=1, quantity="V", description="Grid Voltage"),
    _FloatField(
        "ac_current",
        6,
        precision=2,
        quantity="A",
        description="Grid- / Grid-feeding Current",
    ),
    _IntField("ac_power", 6, quantity="W", description="Delivered (fed-in) Power"),
    _IntField("device_temperature", 2, quantity="°C", description="Device Temperature"),
    _IntField("daily_yield", 7, quantity="Wh", description="Daily Yield"),
    LegacyChecksumField(),
    _StringField("inverter_type", 6),
    _IntField("total_yield", 9, quantity="kWh", description="Total Yield"),
    _LegacyStopField(),
)

# 3 Generic Protocol

FIELDS_SERIAL = (_StartField(), _StringField("serial_number"), _CrcAndStopField())


def _build_mpp_fields(index: int):
    return (
        _FloatField(
            f"dc_mppt{index}_voltage",
            quantity="V",
            description=f"DC Voltage of MPPT{index}",
        ),
        _FloatField(
            f"dc_mppt{index}_current",
            quantity="A",
            description=f"DC Current of MPPT{index}",
        ),
        _IntField(
            f"dc_mppt{index}_power",
            quantity="W",
            description=f"DC Power of MPPT{index}",
        ),
    )


_DC_FIELDS = (
    _FloatField("dc_voltage", quantity="V", description="DC Voltage"),
    _FloatField("dc_current", quantity="A", description="DC Current"),
)

_AC_FIELDS = (
    _FloatField("ac_phase1_voltage", quantity="V", description="AC Voltage of Phase 1"),
    _FloatField("ac_phase1_current", quantity="A", description="AC Current of Phase 1"),
    _FloatField("ac_phase2_voltage", quantity="V", description="AC Voltage of Phase 2"),
    _FloatField("ac_phase2_current", quantity="A", description="AC Current of Phase 2"),
    _FloatField("ac_phase3_voltage", quantity="V", description="AC Voltage of Phase 3"),
    _FloatField("ac_phase3_current", quantity="A", description="AC Current of Phase 3"),
)

_COMMON_POWER_FIELDS = (
    _IntField("dc_power", quantity="W", description="DC Power"),
    _IntField("ac_power", quantity="W", description="AC Power"),
)
_COMMON_MISC_FIELDS = (
    _CosPhiField("cos_phi"),
    _FloatField(
        "device_temperature", quantity="°C", description="Circuit Board Temperature"
    ),
    _IntField("daily_yield", quantity="Wh", description="Daily Yield"),
)


# 3.3.1 Payload of Powador 16.0-18.0 TR3
_GENERIC_SCHMEMA_331_TYPES = {"160TR", "180TR"}

# 3.3.2 Payload of Powador 12.0-20.0 TL3/blueplanet 3.0-5.0 TL1/blueplanet 3.0-10.0 TL3/blueplanet 15.0 TL3 - 20.0 TL3
_GENERIC_SCHMEMA_332_TYPES = {
    "30L11",
    "30L12",
    "35L12",
    "37L12",
    "40L12",
    "46L12",
    "50L12",
    "30L32",
    "40L32",
    "50L32",
    "65L32",
    "75L32",
    "86L32",
    "90L32",
    "100L32",
    "150L32",
    "200L32",
    "3X24",
    "5X24",
    "8X24",
    "10X24",
    "12X24",
    "15X24",
    "20X24",
}

# 3.3.3 Payload of Powador 30.0-72.0 TL3/blueplanet 29.0 TL3 / blueplanet 50.0+60.0 TL3 and TL3 M3-Types
_GENERIC_SCHMEMA_333_TYPES = {
    "375TL",
    "390TL",
    "400TL",
    "480TL",
    "600TL",
    "720TL",
    "29kH3P",
    "50KH3P",
    "50kH4",
    "50kRPO",
    "60kH3P",
    "BG0501",
    "BG50TL",
    "BQ50TL",
    "92G14",
    "110G15",
    "137G16",
}

# 3.3.4 Payload of Powador XP100-350, TL3 M1 Types
_GENERIC_SCHMEMA_334_TYPES = {
    "360M1",
    "390M150kH4P",
    "100kTR",
    "200kTR",
    "200kTL",
    "250kTR250kTL",
    "350kTL",
    "32kH4P",
    "40kH4P",
}


# 3.3.5 Payload of blueplanet 87.0 – 165 TL3
_GENERIC_SCHMEMA_335_TYPES = {
    "87N13",
    "92N14",
    "100N13",
    "105N14",
    "110N15",
    "125N15",
    "125N16",
    "137N16",
    "150N17",
    "155N16",
    "165N17",
}


def _resolve_subfields(inverter_type: str) -> list[_Field]:
    if (
        inverter_type in _GENERIC_SCHMEMA_331_TYPES
        or inverter_type in _GENERIC_SCHMEMA_333_TYPES
    ):
        return [
            *_build_mpp_fields(1),
            *_build_mpp_fields(2),
            *_build_mpp_fields(3),
            *_AC_FIELDS,
            *_COMMON_POWER_FIELDS,
            *_COMMON_MISC_FIELDS,
        ]

    if inverter_type in _GENERIC_SCHMEMA_332_TYPES:
        return [
            *_build_mpp_fields(1),
            *_build_mpp_fields(2),
            *_AC_FIELDS,
            *_COMMON_POWER_FIELDS,
            *_COMMON_MISC_FIELDS,
        ]

    if inverter_type in _GENERIC_SCHMEMA_334_TYPES:
        return [
            *_DC_FIELDS,
            *_AC_FIELDS,
            *_COMMON_POWER_FIELDS,
            *_COMMON_MISC_FIELDS,
        ]
    if inverter_type in _GENERIC_SCHMEMA_335_TYPES:
        return [
            *_DC_FIELDS,
            *_AC_FIELDS,
            _IntField("dc_power", quantity="W", description="DC Power"),
            _FloatField("ac_power", quantity="W", description="AC Power"),
            _FloatField("ac_frequency", description="AC Frequency", quantity="Hz"),
            *_COMMON_MISC_FIELDS,
        ]

    raise ProtocolException(
        f"Can not resolve field schema for inverter type '{inverter_type}'"
    )


class _GenericPayloadField(_Field):
    def read(
        self,
        frame: bytes,
        position: int,
        dest_dict: dict[str, typing.Any],
        *args,
        **kwargs,
    ) -> int:
        number_of_elements = dest_dict["number_of_elements"]
        inverter_type = dest_dict["inverter_type"]
        subfields = _resolve_subfields(inverter_type)
        if (len(subfields) + 3) != number_of_elements:
            raise ProtocolException(
                f"Expected {len(subfields) + 3} elements for type '{inverter_type}', "
                f"got {number_of_elements}"
            )
        for subfield in subfields:
            position = subfield.read(frame, position, dest_dict, *args, **kwargs)

        return position


BASE_FIELDS_GENERIC = (
    _StartField(),
    _IntField("number_of_elements"),
    _StringField("inverter_type"),
    _IntField("status"),
    _GenericPayloadField(),
    _CrcAndStopField(),
)
