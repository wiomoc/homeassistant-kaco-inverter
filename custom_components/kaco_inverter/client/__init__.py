"""Client for connecting to KACO inverters and reading current values."""


class ProtocolException(Exception):
    """Exception raised because a protocol error while commoncating with the inverter."""
