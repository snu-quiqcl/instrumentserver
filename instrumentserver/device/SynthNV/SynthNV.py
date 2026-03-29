"""SynthNV QCoDeS Driver"""

from qcodes import validators as vals
from qcodes.instrument import InstrumentBaseKWArgs

from typing_extensions import Unpack

from ..SerialPortInstrument import SerialPortInstrument


class SynthNV(SerialPortInstrument):
    """QCoDeS driver for controlling SynthNV.
    This driver also manages serial port communication.

    Frequency range: [34.0e6, 4.4e9] Hz
    Power level range: [0, 63]
    """

    def __init__(
        self, name: str, port: str, **kwargs: "Unpack[InstrumentBaseKWArgs]"
    ) -> None:
        super().__init__(name, port, **kwargs)

        self.output = self.add_parameter(
            "output",
            label="RF Output",
            get_cmd=lambda: int(self.ask("o?")),
            set_cmd=lambda o: self.write(f"o{o}"),
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

        self.power = self.add_parameter(
            "power",
            label="Power (dBm)",
            unit="dBm",
            get_cmd=lambda: self.ask("w"),
            get_parser=float,
        )

        self.power_level = self.add_parameter(
            "power_level",
            label="Power Level",
            get_cmd=lambda: self.ask("a?"),
            get_parser=int,
            set_cmd=lambda power_level: self.write(f"a{power_level}"),
            vals=vals.Ints(0, 63),
        )

        self.high_power = self.add_parameter(
            "high_power",
            label="High Power",
            get_cmd=lambda: self.ask("h?"),
            get_parser=lambda res: bool(int(res)),
            set_cmd=lambda is_high: self.write(f"h{int(is_high)}"),
            vals=vals.Bool(),
        )

    def get_idn(self) -> dict[str, str | None]:
        return {
            "vendor": "Windfreak",
            "model": self.ask("+"),
            "serial": self.ask("-"),
            "firmware": self.ask("v"),
        }
