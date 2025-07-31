"""SynthHD (v1.4) QCoDeS Driver"""

from __future__ import annotations

from qcodes import validators as vals
from qcodes.instrument import InstrumentChannel, InstrumentBaseKWArgs

from typing_extensions import Unpack

from ..SerialPortInstrument import SerialPortInstrument


def select_channel(func):
    """Decorator that selects the SynthHD channel before calling func."""

    def wrapper(self, *args, **kwargs):
        self.write(f"C{self.channel_no}")
        ret = func(self, *args, **kwargs)
        return ret

    return wrapper


class SynthHDChannel(InstrumentChannel):
    """Class that implements a SynthHD (v1.4) Output Channel."""

    def __init__(
        self,
        parent: SynthHD,
        name: str,
        channel_no: int,
        **kwargs: "Unpack[InstrumentBaseKWArgs]",
    ):
        super().__init__(parent, name, **kwargs)
        self.channel_no = channel_no

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
            get_cmd=self._read_frequency,
            set_cmd=self._apply_frequency,
            vals=vals.Numbers(53.0e6, 13999.999999e6),
        )

        self.power = self.add_parameter(
            "power",
            label="Power",
            unit="dBm",
            get_cmd=self._read_power,
            set_cmd=self._apply_power,
            vals=vals.Numbers(-80.0, 20.0),
        )

    @select_channel
    def _enable_output(self, o: int) -> None:
        self.write(f"E{o}")  # PLL enable
        self.write(f"r{o}")  # PA enable
        self.write(f"h{o}")  # RF enable

    @select_channel
    def _is_output_enabled(self) -> bool:
        return "1" == self.ask("h?") and "1" == self.ask("r?") and "1" == self.ask("E?")

    @select_channel
    def _read_frequency(self) -> float:
        return float(self.ask("f?")) * 1e6

    @select_channel
    def _apply_frequency(self, freq: float) -> None:
        self.write(f"f{freq/1e6:.8f}")

    @select_channel
    def _read_power(self) -> float:
        return float(self.ask("W?"))

    @select_channel
    def _apply_power(self, power: float) -> None:
        self.write(f"W{power:.3f}")


class SynthHD(SerialPortInstrument):
    """QCoDeS driver for SynthHD (v1.4), a dual channel RF signal generator.
    This driver also manages serial port communication.

    Frequency range: [53.0e6, 13999.999999e6] Hz
    Power range: [-80, 20] dBm

    Frequency resolution: 0.1 Hz
    Power resolution: 0.01 dBm
    """

    def __init__(self, name: str, port: str, **kwargs: "Unpack[InstrumentBaseKWArgs]"):
        super().__init__(name, port, **kwargs)

        for ch_num in range(2):
            ch_name = f"ch{chr(ch_num + 65)}"  # 0 -> chA, 1 -> chB
            channel = SynthHDChannel(self, ch_name, ch_num)
            self.add_submodule(ch_name, channel)

    def get_idn(self) -> dict[str, str | None]:
        return {
            "vendor": "Windfreak",
            "model": self.ask("+"),
            "serial": self.ask("-"),
            "firmware": self.ask("v0"),
        }
