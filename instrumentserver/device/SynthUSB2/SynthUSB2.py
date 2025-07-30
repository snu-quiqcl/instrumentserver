"""SynthUSB2 QCoDeS Driver"""

from qcodes import validators as vals
from qcodes.instrument import InstrumentBaseKWArgs

from typing_extensions import Unpack

from ..SerialPortInstrument import SerialPortInstrument


class SynthUSB2(SerialPortInstrument):
    """QCoDeS driver for SynthUSB2, a RF signal generator.
    This driver also manages serial port communication.

    Frequency range: [34.0e6, 4.4e9] Hz
    Power level range: [0, 3] (0: -4 dBm, 1: -1 dBm, 2: 2 dBm, 3: 5 dBm)
    """

    def __init__(
        self, name: str, port: str, **kwargs: "Unpack[InstrumentBaseKWArgs]"
    ) -> None:
        super().__init__(name, port, **kwargs)

        self.output = self.add_parameter(
            "output",
            label="RF Output",
            get_cmd=self._is_output_enabled,
            get_parser=int,
            set_cmd=self._enable_output,
            val_mapping={"OFF": 0, "ON": 1},
        )

        self.frequency = self.add_parameter(
            "frequency",
            label="Frequency",
            unit="Hz",
            get_cmd=lambda: self.ask("f?"),
            get_parser=lambda freq_str: float(freq_str) * 1e6,
            set_cmd=lambda freq: self.write(f"f{freq/1e6:.3f}"),
            vals=vals.Numbers(34.0e6, 4.4e9),
        )

        self.power_level = self.add_parameter(
            "power_level",
            label="Power Level",
            get_cmd=lambda: self.ask("a?"),
            get_parser=int,
            set_parser=lambda power_level: self.write(f"a{power_level}"),
            vals=vals.Ints(0, 3),
        )

    def _enable_output(self, o: int) -> None:
        self.write(f"h{o}")  # RF high power
        self.write(f"o{o}")  # RF on

    def _is_output_enabled(self) -> bool:
        return "1" == self.ask("o?") and "1" == self.ask("h?")

    def get_idn(self) -> dict[str, str | None]:
        return {
            "vendor": "Windfreak",
            "model": self.ask("+"),
            "serial": self.ask("-"),
            "firmware": self.ask("v"),
        }
