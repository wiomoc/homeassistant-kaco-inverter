import abc
from dataclasses import dataclass
import typing

import crc

from . import ProtocolException


class Field(typing.Protocol):
    def read(
        self,
        frame: bytes,
        position: int,
        dest_dict: dict[str, typing.Any],
        annotate: bool,
    ) -> int: ...


def expect_min_remaining_frame_length(
    frame: bytes, position: int, expected_length: int
) -> None:
    if len(frame) < (position + expected_length):
        raise ProtocolException("Unexpected end-of-frame")


def _expect_char(frame: bytes, position: int, char: str) -> None:
    assert len(char) == 1
    if frame[position] != ord(char):
        raise ProtocolException(
            f"Expected '{char}', got {frame[position : position + 1]}"
        )


@dataclass
class AnnotatedValue[T]:
    value: T
    quantity: str
    description: str


class ValueField[T](Field, abc.ABC):
    _name: str
    _length: int | None
    _quantity: str | None
    _description: str | None

    def __init__(
        self,
        name: str,
        length: int | None = None,
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
        pass


class StringField(ValueField[str]):
    def parse(self, field_value_bytes: bytes) -> str:
        try:
            return field_value_bytes.lstrip(b"\0").decode("ASCII").lstrip()
        except UnicodeDecodeError as e:
            raise ProtocolException(
                f"Expected ASCII characters, got {field_value_bytes}"
            ) from e


class IntField(ValueField[int]):
    def parse(self, field_value_bytes: bytes) -> int:
        try:
            field_value_string = field_value_bytes.decode("ASCII").lstrip()
            return int(field_value_string)
        except (UnicodeDecodeError, ValueError) as e:
            raise ProtocolException(
                f"Expected integer, got {field_value_bytes}"
            ) from e


class FloatField(ValueField[float]):
    _precision: int | None

    def __init__(
        self,
        name: str,
        length: int | None = None,
        precision: int | None = None,
        *args,
        **kwargs,
    ):
        super().__init__(name, length, *args, **kwargs)
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
            raise ProtocolException(f"Expected float, got {field_value_bytes}") from e


class CosPhiField(FloatField):
    def parse(self, field_value_bytes: bytes) -> float:
        if field_value_bytes[-1:] not in {b"c", b"i", b"o"}:
            raise ProtocolException(
                f"Expected c, i or o, got {field_value_bytes[-1:]}"
            )
        return super().parse(field_value_bytes[:-1])


class DurationField(ValueField[int]):
    def parse(self, field_value_bytes: bytes) -> int:
        _expect_char(field_value_bytes, -3, ":")
        try:
            field_value_string = field_value_bytes.decode("ASCII").lstrip()
            hours = int(field_value_string[:-3])
            minutes = int(field_value_string[-2:])
            return 60 * hours + minutes
        except (UnicodeDecodeError, ValueError) as e:
            raise ProtocolException(f"Expected duration, got '{field_value_bytes}'") from e


class LegacyChecksumField(Field):
    def read(self, frame: bytes, position: int, *args, **kwargs) -> int:
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


class StartField(Field):
    def read(self, frame: bytes, position: int, *args, **kwargs) -> int:
        length = 5
        assert position == 0
        expect_min_remaining_frame_length(frame, position, length)
        _expect_char(frame, position, "\n")
        _expect_char(frame, position + 1, "*")
        try:
            frame[2:position].decode("ASCII")
        except (UnicodeDecodeError, ValueError) as e:
            raise ProtocolException(
                f"Expected address and command, got {frame[2:position]}"
            ) from e

        return position + length


class LegacyStopField(Field):
    def read(self, frame: bytes, position: int, *args, **kwargs) -> int:
        expect_min_remaining_frame_length(frame, position, 1)
        _expect_char(frame, position, "\r")
        if len(frame) > (position + 1):
            raise ProtocolException("Expected end-of-frame")
        return position + 1


_crc_calculator = crc.Calculator(crc.Crc16.X25.value)


class CrcAndStopField(Field):
    def read(self, frame: bytes, position: int, *args, **kwargs):
        length = 6
        expect_min_remaining_frame_length(frame, position, length)
        _expect_char(frame, position, " ")
        crc_hex = frame[position + 1 : position + 5]
        try:
            expected_crc = int(crc_hex.decode("ASCII"), 16)
        except (UnicodeDecodeError, ValueError) as e:
            raise ProtocolException(f"Expected hex, got {crc_hex}") from e

        crc_dc_bytes = frame[1 : position + 1]
        actual_crc = _crc_calculator.checksum(crc_dc_bytes)
        if actual_crc != expected_crc:
            raise ProtocolException(f"Expected CRC {expected_crc:02X}, got {actual_crc:02X}")

        _expect_char(frame, position + 5, "\r")

        if len(frame) > position + length:
            raise ProtocolException("Expected end-of-frame")


FIELDS_00_02 = (
    StartField(),
    IntField("status", 3),
    FloatField(
        "dc_voltage", 5, precision=1, quantity="V", description="Generator Voltage"
    ),
    FloatField(
        "dc_current", 5, precision=2, quantity="A", description="Generator Current"
    ),
    IntField("dc_power", 5, quantity="W", description="Generator Power"),
    FloatField("ac_voltage", 5, precision=1, quantity="V", description="Grid Voltage"),
    FloatField(
        "ac_current",
        5,
        precision=2,
        quantity="A",
        description="Grid- / Grid-feeding Current",
    ),
    IntField("ac_power", 5, quantity="W", description="Delivered (fed-in) Power"),
    IntField("device_temperature", 3, quantity="°C", description="Device Temperature"),
    IntField("daily_yield", 6, quantity="Wh", description="Daily Yield"),
    LegacyChecksumField(),
    StringField("inverter_type", 6),
    LegacyStopField(),
)

FIELDS_000XI = (
    StartField(),
    IntField("status", 3),
    FloatField(
        "dc_voltage", 5, precision=1, quantity="V", description="Generator Voltage"
    ),
    FloatField(
        "dc_current", 5, precision=2, quantity="A", description="Generator Current"
    ),
    IntField("dc_power", 6, quantity="W", description="Generator Power"),
    FloatField("ac_voltage", 5, precision=1, quantity="V", description="Grid Voltage"),
    FloatField(
        "ac_current",
        5,
        precision=2,
        quantity="A",
        description="Grid- / Grid-feeding Current",
    ),
    IntField("ac_power", 6, quantity="W", description="Delivered (fed-in) Power"),
    IntField("device_temperature", 2, quantity="°C", description="Device Temperature"),
    IntField("daily_yield", 6, quantity="Wh", description="Daily Yield"),
    LegacyChecksumField(),
    StringField("inverter_type", 4),
    LegacyStopField(),
)

FIELDS_XP = (
    StartField(),
    IntField("status", 3),
    FloatField(
        "dc_voltage", 5, precision=1, quantity="V", description="Generator Voltage"
    ),
    FloatField(
        "dc_current", 6, precision=2, quantity="A", description="Generator Current"
    ),
    IntField("dc_power", 6, quantity="W", description="Generator Power"),
    FloatField("ac_voltage", 5, precision=1, quantity="V", description="Grid Voltage"),
    FloatField(
        "ac_current",
        6,
        precision=2,
        quantity="A",
        description="Grid- / Grid-feeding Current",
    ),
    IntField("ac_power", 6, quantity="W", description="Delivered (fed-in) Power"),
    IntField("device_temperature", 2, quantity="°C", description="Device Temperature"),
    IntField("daily_yield", 7, quantity="Wh", description="Daily Yield"),
    LegacyChecksumField(),
    StringField("inverter_type", 6),
    IntField("total_yield", 9, quantity="kWh", description="Total Yield"),
    LegacyStopField(),
)

FIELDS_SERIAL = (StartField(), StringField("serial_number"), CrcAndStopField())


def _build_mpp_fields(index: int):
    return (
        FloatField(
            f"dc_mppt{index}_voltage",
            quantity="V",
            description=f"DC Voltage of MPPT{index}",
        ),
        FloatField(
            f"dc_mppt{index}_current",
            quantity="A",
            description=f"DC Current of MPPT{index}",
        ),
        IntField(
            f"dc_mppt{index}_power",
            quantity="W",
            description=f"DC Power of MPPT{index}",
        ),
    )


_AC_FIELDS = (
    FloatField("ac_phase1_voltage", quantity="V", description="AC Voltage of Phase 1"),
    FloatField("ac_phase1_current", quantity="A", description="AC Current of Phase 1"),
    FloatField("ac_phase2_voltage", quantity="V", description="AC Voltage of Phase 2"),
    FloatField("ac_phase2_current", quantity="A", description="AC Current of Phase 2"),
    FloatField("ac_phase3_voltage", quantity="V", description="AC Voltage of Phase 3"),
    FloatField("ac_phase3_current", quantity="A", description="AC Current of Phase 3"),
)

_COMMON_POWER_FIELDS = (
    IntField("dc_power", quantity="W", description="DC Power"),
    IntField("ac_power", quantity="W", description="AC Power"),
)
_COMMON_MISC_FIELDS = (
    CosPhiField("cos_phi"),
    FloatField(
        "device_temperature", quantity="°C", description="Circuit Board Temperature"
    ),
    IntField("daily_yield", quantity="Wh", description="Daily Yield"),
)


def _resolve_subfields(inverter_type: str) -> list[Field]:
    return [
        *_build_mpp_fields(1),
        *_build_mpp_fields(2),
        *_AC_FIELDS,
        *_COMMON_POWER_FIELDS,
        *_COMMON_MISC_FIELDS,
    ]


class GenericPayloadField(Field):
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
                f"Expected {len(subfields) + 3} elements for type '{inverter_type}', got {number_of_elements}"
            )
        for subfield in subfields:
            position = subfield.read(frame, position, dest_dict, *args, **kwargs)

        return position


FIELDS_GENERIC = (
    StartField(),
    IntField("number_of_elements"),
    StringField("inverter_type"),
    IntField("status"),
    GenericPayloadField(),
    CrcAndStopField(),
)
