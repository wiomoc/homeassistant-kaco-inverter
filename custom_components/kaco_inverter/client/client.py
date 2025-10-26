from collections.abc import Iterable
from types import TracebackType
import typing

from serial import Serial, SerialException

from . import ProtocolException
from .fields import (
    FIELDS_00_02,
    FIELDS_000XI,
    FIELDS_GENERIC,
    FIELDS_SERIAL,
    FIELDS_XP,
    Field,
    LegacyChecksumField,
    expect_min_remaining_frame_length,
)


class KacoInverterClient:
    _port: Serial
    _address: int  # + m, n
    _is_000xi: bool
    _infered_standard_fields: tuple[Field, ...] | None

    @staticmethod
    def create_port(port_name: str):
        return Serial(port_name, baudrate=9600, timeout=2, write_timeout=1)

    def __init__(self, port: str | Serial, address: int) -> None:
        assert 1 <= address <= 99
        self._address = address
        self._is_000xi = False
        self._infered_standard_fields = None
        if isinstance(port, str):
            self._port = KacoInverterClient.create_port(port)
        else:
            self._port = port

    def _send_command(self, command: str) -> tuple[str, bytes]:
        try:
            self._port.reset_input_buffer()
            self._port.write(f"#{self._address:02}{command}\r".encode("ASCII"))
            self._port.flush()
            response = self._port.read_until(b"\r")
        except SerialException as e:
            raise ProtocolException("Serial port error") from e
        expect_min_remaining_frame_length(response, 0, 5)
        field_value_bytes = response[:5]
        try:
            header = field_value_bytes.decode("ASCII")
            address = int(header[2:4])
            command = header[4]
        except (UnicodeDecodeError, ValueError) as e:
            raise ProtocolException(
                f"Expected ASCII characters, got {field_value_bytes}"
            ) from e
        else:
            if address != self._address:
                raise ProtocolException(
                    f"Expected response from '{self._address}', got response from '{address}'"
                )

            return command, response

    def _parse_fields(
        self, fields: Iterable[Field], message: bytes, annotate: bool = False
    ) -> dict[str, typing.Any]:
        position = 0
        data_dict = {}
        for field in fields:
            position = field.read(message, position, data_dict, annotate=annotate)
            # Previous .read_until(b"\r") could have been only read until after the legacy checksum
            # as the checksum byte could be "\r" too.
            if position == len(message) and isinstance(field, LegacyChecksumField):
                try:
                    message += self._port.read_until(b"\r")
                except SerialException as e:
                    raise ProtocolException("Serial port error") from e
        return data_dict

    def _handle_kaco_standard_readings(
        self, message: bytes, annotate: bool = False
    ) -> dict[str, typing.Any]:
        if self._infered_standard_fields:
            return self._parse_fields(
                self._infered_standard_fields, message, annotate=annotate
            )
        try:
            data_dict = self._parse_fields(FIELDS_00_02, message, annotate=annotate)
            self._infered_standard_fields = FIELDS_00_02
        except ProtocolException:
            data_dict = self._parse_fields(FIELDS_XP, message, annotate=annotate)
            self._infered_standard_fields = FIELDS_XP

        return data_dict

    def _query_000xi_readings(self, annotate: bool = False) -> dict[str, typing.Any]:
        data_dict = {}
        for index in ["1", "2", "3"]:
            reponse_command, message = self._send_command(index)
            assert reponse_command == index
            sub_data_dict = self._parse_fields(FIELDS_000XI, message, annotate=annotate)
            for key, value in sub_data_dict.items():
                data_dict[f"{index}_{key}"] = value
        # 8k1 -> 3x8k, 10k1 -> 3x10k, 11k1 -> 3x11k
        data_dict["inverter_type"] = f"3x{data_dict['1_inverter_type'][:-1]}"
        self._is_000xi = True
        return data_dict

    def _handle_generic_readings(
        self, message: bytes, annotate: bool = False
    ) -> dict[str, typing.Any]:
        return self._parse_fields(FIELDS_GENERIC, message, annotate=annotate)

    def query_readings(self, annotate: bool = False) -> dict[str, typing.Any]:
        if self._is_000xi:
            return self._query_000xi_readings(annotate=annotate)
        response_command, response = self._send_command("0")
        if response_command == "0":
            return self._handle_kaco_standard_readings(response, annotate=annotate)
        if response_command == "4":
            return self._query_000xi_readings(annotate=annotate)
        if response_command == "n":
            return self._handle_generic_readings(response, annotate=annotate)
        raise ProtocolException(
            f"Expected '0', '4' or 'n' command response, got '{response_command}'"
        )

    def query_serial_number(self) -> str:
        response_command, response = self._send_command("s")
        if response_command != "s":
            raise ProtocolException(
                f"Expected 's' command response, got {response_command}"
            )
        data_dict = self._parse_fields(FIELDS_SERIAL, response)
        return data_dict["serial_number"]

    def __enter__(self) -> typing.Self:
        if not self._port.is_open:
            self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        if self._port.is_open:
            self.close()

    def open(self):
        self._port.open()

    def close(self):
        self._port.close()
