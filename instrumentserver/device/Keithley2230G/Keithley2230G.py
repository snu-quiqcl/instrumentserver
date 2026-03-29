"""QCoDeS driver for the Keithley2230G power supply."""

from typing_extensions import Unpack

from qcodes.instrument import (
    Instrument,
    InstrumentChannel,
    VisaInstrument,
    InstrumentBaseKWArgs,
    VisaInstrumentKWArgs,
)
from qcodes import validators as vals


class Keithley2230GChannel(InstrumentChannel):
    def __init__(
        self,
        parent: Instrument,
        name: str,
        channel: int,
        voltage_limit: float = 60.0,
        current_limit: float = 3.0,
        **kwargs: "Unpack[InstrumentBaseKWArgs]",
    ) -> None:
        super().__init__(parent, name, **kwargs)
        self.channel = channel

        self.voltage = self.add_parameter(
            "voltage",
            label=f"Channel {channel} Voltage",
            unit="V",
            get_cmd=self._get_voltage,
            get_parser=float,
        )

        self.current = self.add_parameter(
            "current",
            label=f"Channel {channel} Current",
            unit="A",
            get_cmd=self._get_current,
            get_parser=float,
            vals=vals.Numbers(0, current_limit),
        )

        self.power = self.add_parameter(
            "power",
            label=f"Channel {channel} Power",
            unit="W",
            get_cmd=self._get_power,
            get_parser=float,
            vals=vals.Numbers(),
        )

        self.target_voltage = self.add_parameter(
            "target_voltage",
            label=f"Channel {channel} Target Voltage",
            unit="V",
            get_cmd=self._get_target_voltage,
            get_parser=float,
            set_cmd=self._set_target_voltage,
            vals=vals.Numbers(0, voltage_limit),
        )

        self.target_current = self.add_parameter(
            "target_current",
            label=f"Channel {channel} Target Current",
            unit="A",
            get_cmd=self._get_target_current,
            get_parser=float,
            set_cmd=self._set_target_current,
            vals=vals.Numbers(0, current_limit),
        )

        self.output = self.add_parameter(
            "output",
            label=f"Channel {channel} Output",
            set_parser=int,
            get_parser=bool,
            get_cmd=self._get_output,
            set_cmd=self._set_output,
            vals=vals.Bool(),
        )

        self.voltage_limit = self.add_parameter(
            "voltage_limit",
            label=f"Channel {channel} Voltage Limit",
            unit="V",
            get_cmd=self._get_voltage_limit,
            get_parser=float,
            set_cmd=self._set_voltage_limit,
            vals=vals.Numbers(0, 30) if channel != 3 else vals.Numbers(0, 5),
        )

        self.voltage_limit_state = self.add_parameter(
            "voltage_limit_state",
            label=f"Channel {channel} Voltage Limit State",
            get_cmd=self._get_voltage_limit_state,
            get_parser=bool,
            set_cmd=self._set_voltage_limit_state,
            vals=vals.Bool(),
        )

    def _select_channel(self) -> None:
        self.parent.write(f"INST CH{self.channel}")

    def _get_voltage(self) -> float:
        self._select_channel()
        # return self.parent.ask(f"MEASure:VOLTage? CH{self.channel}")
        return self.parent.ask(f"FETCh:VOLTage? CH{self.channel}")

    def _get_current(self) -> float:
        self._select_channel()
        # return self.parent.ask(f"MEASure:CURRent? CH{self.channel}")
        return self.parent.ask(f"FETCh:CURRent? CH{self.channel}")

    def _get_power(self) -> float:
        self._select_channel()
        # return self.parent.ask(f"MEASure:POWer? CH{self.channel}")
        return self.parent.ask(f"FETCh:POWer? CH{self.channel}")

    def _get_target_voltage(self) -> float:
        self._select_channel()
        return self.parent.ask("VOLT?")

    def _set_target_voltage(self, voltage: float) -> None:
        self._select_channel()
        self.parent.write(f"VOLT {voltage}")

    def _get_target_current(self) -> float:
        self._select_channel()
        return self.parent.ask("CURR?")

    def _set_target_current(self, current: float):
        self._select_channel()
        self.parent.write(f"CURR {current}")

    def _get_output(self) -> bool:
        self._select_channel()
        return bool(int(self.parent.ask("CHAN:OUTP?")))

    def _set_output(self, state: bool) -> None:
        self._select_channel()
        self.parent.write(f"CHAN:OUTP {int(state)}")

    def _set_voltage_limit(self, limit: float):
        """Set the voltage limit for the channel."""
        self._select_channel()
        self.parent.write(f"VOLT:LIM {float(limit)}")

    def _get_voltage_limit(self) -> float:
        """Get the voltage limit for the channel."""
        self._select_channel()
        return float(self.parent.ask("VOLT:LIM?"))

    def _set_voltage_limit_state(self, state: bool):
        """Set the voltage limit state for the channel."""
        self._select_channel()
        self.parent.write(f"VOLT:LIM:STATe {int(state)}")

    def _get_voltage_limit_state(self) -> bool:
        """Get the voltage limit state for the channel."""
        self._select_channel()
        return bool(int(self.parent.ask("VOLT:LIM:STATe?")))


class Keithley2230G(VisaInstrument):
    def __init__(
        self,
        name: str,
        address: str,
        **kwargs: "Unpack[VisaInstrumentKWArgs]",
    ):
        # Keithley 2230G does not support the clear buffer command for some reason.
        super().__init__(name, address, device_clear=False, **kwargs)

        for ch_num in [1, 2, 3]:
            ch_name = f"ch{ch_num}"
            channel = Keithley2230GChannel(self, ch_name, ch_num)
            self.add_submodule(ch_name, channel)


class Keithley2230G_30_6(VisaInstrument):
    def __init__(
        self,
        name: str,
        address: str,
        **kwargs: "Unpack[VisaInstrumentKWArgs]",
    ):
        # Keithley 2230G does not support the clear buffer command for some reason.
        super().__init__(name, address, device_clear=False, **kwargs)
        self.voltage_limits = [30.0, 30.0, 5.0]  # Voltage limits for channels 1, 2, and 3
        self.current_limits = [6.0, 6.0, 3.0]  # Current limits for channels 1, 2, and 3

        for i in range(3):
            ch = i + 1
            ch_name = f"ch{ch}"
            channel = Keithley2230GChannel(
                self,
                ch_name,
                ch,
                voltage_limit=self.voltage_limits[i],
                current_limit=self.current_limits[i],
            )
            self.add_submodule(ch_name, channel)


class Keithley2230G_60_3(VisaInstrument):
    def __init__(
        self,
        name: str,
        address: str,
        **kwargs: "Unpack[VisaInstrumentKWArgs]",
    ):
        # Keithley 2230G does not support the clear buffer command for some reason.
        super().__init__(name, address, device_clear=False, **kwargs)
        self.voltage_limits = [60.0, 60.0, 5.0]  # Voltage limits for channels 1, 2, and 3
        self.current_limits = [3.0, 3.0, 3.0]  # Current limits for channels 1, 2, and 3

        for i in range(3):
            ch = i + 1
            ch_name = f"ch{ch}"
            channel = Keithley2230GChannel(
                self,
                ch_name,
                ch,
                voltage_limit=self.voltage_limits[i],
                current_limit=self.current_limits[i],
            )
            self.add_submodule(ch_name, channel)


class Keithley2230GSIM(Instrument):
    """Simulated driver for the Keithley2230G power supply."""

    def __init__(
        self,
        name: str,
    ):
        super().__init__(name)

        for ch_num in [1, 2, 3]:
            ch_name = f"ch{ch_num}"
            channel = Keithley2230GChannelSIM(self, ch_name, ch_num)
            self.add_submodule(ch_name, channel)

    def get_idn(self) -> dict[str, str]:
        """Return the identification of the simulated instrument."""
        return {
            "vendor": "Keithley",
            "model": "2230G",
            "serial": "SIMULATED",
            "firmware": "1.0.0",
        }


class Keithley2230GChannelSIM(Keithley2230GChannel):
    """Simulated channel for the Keithley2230G power supply channel."""

    def __init__(
        self,
        parent: Instrument,
        name: str,
        channel: int,
        **kwargs: "Unpack[InstrumentBaseKWArgs]",
    ) -> None:
        super().__init__(parent, name, channel, **kwargs)

        # Simulated parameters do not require actual hardware interaction.
        self._voltage = 0
        self._current = 0
        self._output = False
        self._voltage_limit = 30 if channel != 3 else 5
        self._voltage_limit_state = False

    def _get_voltage(self):
        print(f"Simulated get voltage for channel {self.channel}")
        return self._voltage

    def _set_voltage(self, voltage):
        self._voltage = voltage

    def _get_current(self):
        return self._current

    def _set_current(self, current):
        self._current = current

    def _get_output(self):
        return self._output

    def _set_output(self, state):
        self._output = state

    def _get_voltage_limit(self):
        return self._voltage_limit

    def _set_voltage_limit(self, limit):
        self._voltage_limit = limit

    def _get_voltage_limit_state(self):
        return self._voltage_limit_state

    def _set_voltage_limit_state(self, state):
        self._voltage_limit_state = state


# Example usage:
if __name__ == "__main__":
    # Change the power supply address to the actual address before testing.
    power_supply_address = "USB0::1510::8752::802901012747310023::0::INSTR"
    keithley2230g = Keithley2230G(name="keithley2230g", address=power_supply_address)
    print(keithley2230g.get_idn())

    keithley2230g.ch1.voltage(0.3)
    keithley2230g.ch1.current(0.01)
    keithley2230g.ch1.output(True)

    print(keithley2230g.ch1.voltage(), "V")
    print(keithley2230g.ch1.current(), "A")
    print(keithley2230g.ch1.output())

    keithley2230g.ch1.output(False)

    keithley2230g.close()
