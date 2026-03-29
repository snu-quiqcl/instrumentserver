"""Base class for all instruments using serial port communication."""

import serial

from qcodes.instrument import Instrument, InstrumentBaseKWArgs

from typing_extensions import Unpack


class SerialPortInstrument(Instrument):
    """Base class for all instruments using serial port communication."""

    def __init__(
        self, name: str, port: str, **kwargs: "Unpack[InstrumentBaseKWArgs]"
    ) -> None:
        super().__init__(name, **kwargs)

        self._port = port
        self._serial = serial.Serial(port=self._port)

    def write(self, cmd: str) -> None:
        super().write(cmd + "\n")

    def write_raw(self, cmd: str) -> None:
        byte_cmd = cmd.encode("ascii")
        written = self._serial.write(byte_cmd)
        if written != len(byte_cmd):
            raise OSError("Failed to completely send the command.")

    def ask(self, cmd: str) -> str:
        return super().ask(cmd + "\n")

    def ask_raw(self, cmd: str) -> str:
        self.write_raw(cmd)

        terminator = b"\n"
        res = self._serial.read_until(terminator)

        return res[:-1].decode("ascii")  # trim terminator

    def close(self) -> None:
        self._serial.close()
        super().close()
