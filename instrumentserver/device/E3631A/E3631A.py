"""E3631A QCoDeS Driver"""

from __future__ import annotations

from qcodes import validators as vals
from qcodes.instrument import InstrumentChannel, InstrumentBaseKWArgs

from typing_extensions import Unpack

from ..SerialPortInstrument import SerialPortInstrument


def select_channel(func):
    """Decorator that selects the E3631A Output before calling func."""

    def wrapper(self, *args, **kwargs):
        self.write(f":INST {self.output_id}")
        ret = func(self, *args, **kwargs)
        return ret

    return wrapper


class E3631AOutput(InstrumentChannel):
    """Class that implements a single E3631A Output."""

    def __init__(
        self,
        parent: E3631A,
        name: str,
        limits: dict[str, float],
        **kwargs: "Unpack[InstrumentBaseKWArgs]",
    ) -> None:
        """
        Args:
            limits: Dictionary with limit conditions.
            The keys should be "[min/max]_[voltage/current]",
            and the values, the corresponding limit values.
        """

        super().__init__(parent, name, **kwargs)
        self.output_id = name.upper()

        self.voltage = self.add_parameter(
            "voltage",
            label="Voltage",
            unit="V",
            get_cmd=self._read_voltage,
            set_cmd=self._apply_voltage,
            vals=vals.Numbers(limits["min_voltage"], limits["max_voltage"]),
        )

        self.current = self.add_parameter(
            "current",
            label="Current",
            unit="A",
            get_cmd=self._read_current,
            set_cmd=self._apply_current,
            vals=vals.Numbers(limits["min_current"], limits["max_current"]),
        )

    @select_channel
    def _enable_output(self) -> None:
        self.write(":OUTP ")

    @select_channel
    def _read_voltage(self) -> float:
        return float(self.ask(":MEAS:VOLT?"))

    @select_channel
    def _apply_voltage(self, voltage: float) -> None:
        return float(self.write(f":VOLT {voltage}"))

    @select_channel
    def _read_current(self) -> float:
        return float(self.ask(":MEAS:CURR?"))

    @select_channel
    def _apply_current(self, current: float) -> None:
        return float(self.write(f":CURR {current}"))


class E3631A(SerialPortInstrument):
    """QCoDeS driver for E3631A, a triple output power supply.
    This driver also manages serial port communication.
    """

    LIMITS = {
        "p6v": {
            "min_voltage": 0,
            "max_voltage": 6.18,
            "min_current": 0,
            "max_current": 5.15,
        },
        "p25v": {
            "min_voltage": 0,
            "max_voltage": 25.75,
            "min_current": 0,
            "max_current": 1.03,
        },
        "n25v": {
            "min_voltage": -25.75,
            "max_voltage": 0,
            "min_current": 0,
            "max_current": 1.03,
        },
    }

    def __init__(
        self, name: str, port: str, **kwargs: "Unpack[InstrumentBaseKWArgs]"
    ) -> None:
        super().__init__(name, port, **kwargs)

        self.output = self.add_parameter(
            "output",
            label="Output",
            get_cmd=lambda: "ON" if "1" == self.ask(":OUTP?") else "OFF",
            set_cmd=lambda o: self.write(f":OUTP {o}"),
            vals=vals.Enum("OFF", "ON"),
        )

        for output_id in ["p6v", "p25v", "n25v"]:
            output = E3631AOutput(self, output_id, self.LIMITS[output_id])
            self.add_submodule(output_id, output)
