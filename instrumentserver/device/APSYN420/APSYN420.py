"""APSYN420 QCoDeS Driver"""

import math
import socket

from qcodes import validators as vals
from qcodes.instrument import Instrument, InstrumentBaseKWArgs

from typing_extensions import Unpack


class APSYN420(Instrument):
    """QCoDeS driver for APSYN420, a high frequency signal generator.
    This class also manages socket communication.

    Power is not adjustable(+23 dBm).

    Frequency range: [10.0e6, 20.0e9] Hz

    Frequency resolution: 0.001 Hz
    Phase resolution: 0.1 deg
    """

    def __init__(
        self,
        name: str,
        tcp_ip: str,
        tcp_port: int | str,
        **kwargs: "Unpack[InstrumentBaseKWArgs]",
    ):
        super().__init__(name, **kwargs)

        self._socket = socket.socket()
        self._tcp_ip = tcp_ip
        self._tcp_port = int(tcp_port)

        self.output = self.add_parameter(
            "output",
            label="RF Output",
            get_cmd=lambda: int(self.ask(":OUTP?")),
            set_cmd=lambda o: self.write(f":OUTP {o}"),
            val_mapping={"OFF": 0, "ON": 1}
        )

        self.frequency = self.add_parameter(
            "frequency",
            label="Frequency",
            unit="Hz",
            get_cmd=lambda: self.ask(":FREQ?"),
            get_parser=float,
            set_cmd=lambda freq: self.write(f"FREQ {freq:.3f}"),
            vals=vals.Numbers(10e6, 20e9)
        )

        self.phase = self.add_parameter(
            "phase",
            label="Phase (deg)",
            unit="deg",
            get_cmd=lambda: self.ask(":PHAS?"),
            get_parser=lambda phase_rad: float(phase_rad) * 180 / math.pi,
            set_cmd=lambda phase_rad: self.write(f"PHAS {phase_rad:.3f}"),
            set_parser=lambda phase_deg: (phase_deg % 360) * math.pi / 180
        )

        self._socket.connect((self._tcp_ip, self._tcp_port))

    def lock(self, ext_ref_freq=10e6) -> None:
        """Conveys the expected reference frequency value of an externally applied reference
        to the signal generator.

        Frequency range: [1, 250] Mhz (default: 10 MHz)

        Raises:
            ValueError - ext_ref_freq is out of range.
        """
        min_, max_ = 1e6, 250e6
        if ext_ref_freq < min_ or ext_ref_freq > max_:
            raise ValueError(
                f"External reference frequency={ext_ref_freq} is out of range: \
                min={min_}, max={max_}"
            )

        self.write(f":ROSC:EXT:FREQ {ext_ref_freq:.0f}")
        self.write(":ROSC:SOUR EXT")

    def is_locked(self) -> bool:
        """Checks if the synthesizer is locked to an externally applied reference."""
        return "1" == self.ask(":ROSC:LOCK?")

    def write(self, cmd: str) -> None:
        super().write(cmd + "\n")

    def write_raw(self, cmd: str) -> None:
        byte_cmd = cmd.encode("ascii")
        sent = self._socket.send(byte_cmd)
        if sent != len(byte_cmd):
            raise OSError("Failed to completely send the command.")

    def ask(self, cmd: str) -> str:
        return super().ask(cmd + "\n")

    def ask_raw(self, cmd: str) -> str:
        self.write_raw(cmd)

        terminator = b"\n"
        res = b""
        while not res.endswith(terminator):
            res += self._socket.recv(1024)  # bufSize = 1024

        return res[:-1].decode("ascii")  # trim terminator

    def close(self) -> None:
        self._socket.close()
        super().close()
