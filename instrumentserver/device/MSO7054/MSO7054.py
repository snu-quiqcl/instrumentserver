"""MSO7054 QCoDeS Driver"""

# TODO: Add a time axis parameter and wave parameter of class ParameterWithSetPoints
# for measurements and plotting.

from __future__ import annotations

from qcodes import validators as vals
from qcodes.instrument import (
    InstrumentChannel,
    VisaInstrument,
    InstrumentBaseKWArgs,
    VisaInstrumentKWArgs,
)

from typing_extensions import Unpack


class MSO7054Channel(InstrumentChannel):
    """Class that implements a MSO7054 Channel."""

    def __init__(
        self,
        parent: MSO7054,
        name: str,
        channel: int,
        **kwargs: "Unpack[InstrumentBaseKWArgs]",
    ):
        super().__init__(parent, name, **kwargs)
        self.channel = channel

        self.active = self.add_parameter(
            "active",
            label="Active",
            get_cmd=f":CHAN{self.channel}:DISP?",
            get_parser=int,
            set_parser=f":CHAN{self.channel}:DISP {{}}",
            val_mapping={"OFF": 0, "ON": 1},
        )

        self.sample_rate = self.add_parameter(
            "sample_rate",
            label="Sample Rate",
            get_cmd=f":ACQ:SRAT? CHAN{self.channel}",
            get_parser=float,
            set_cmd=False,
        )

        self.amp_scale = self.add_parameter(
            "amp_scale",
            label="Amplitude Scale",
            unit="V",
            get_cmd=f":CHAN{self.channel}:SCAL?",
            get_parser=float,
            set_cmd=f":CHAN{self.channel}:SCAL {{:.3f}}",
        )

        self.amp_offset = self.add_parameter(
            "amp_offset",
            label="Amplitude Offset",
            unit="V",
            get_cmd=f":CHAN{self.channel}:OFFS?",
            get_parser=float,
            set_cmd=f"CHAN{self.channel}:OFFS {{:.3f}}",
        )

        self.wave_data = self.add_parameter(
            "wave_data",
            label="Raw Wave Data",
            get_cmd=self._get_wave_data,
            set_cmd=False,
        )

        for key in ["vmax", "vmin", "vrms", "vav"]:
            setattr(
                self,
                key,
                self.add_parameter(
                    key,
                    label=key.upper(),
                    unit="V",
                    get_cmd=f":MEAS:ITEM? {key.upper()},CHAN{self.channel}",
                    get_parser=float,
                    set_parser=False,
                ),
            )

        self.vpp = self.add_parameter(
            "vpp",
            label="VPP",
            unit="Vpp",
            get_cmd=f":MEAS:ITEM? VPP,CHAN{self.channel}",
            set_parser=False,
        )

        self.freq = self.add_parameter(
            "freq",
            label="FREQ",
            unit="Hz",
            get_cmd=f":MEAS:ITEM? FREQ,CHAN{self.channel}",
            get_parser=float,
            set_parser=False,
        )

    def _get_wave_data(self):
        self.write(":WAV:MODE NORM")
        self.write(":WAV:FORM BYTE")
        self.write(f":WAV:SOUR CHAN{self.channel}")
        self.parent.visa_handle.query_binary_values(
            f":WAV:DATA? CHAN{self.channel}", datatype="B"
        )


class MSO7054(VisaInstrument):
    """QCoDeS driver for MSO7054, an oscilloscope."""

    default_terminator = "\n"

    def __init__(
        self, name: str, address: str, **kwargs: "Unpack[VisaInstrumentKWArgs]"
    ):
        super().__init__(name, address, **kwargs)

        self.auto = self.add_parameter(
            "auto",
            label="AUTO",
            get_cmd=":SYST:AUTO?",
            get_parser=int,
            set_cmd=":SYST:AUTO {}",
            val_mapping={"OFF": 0, "ON": 1},
        )

        self.mem_depth = self.add_parameter(
            "mem_depth",
            label="Memory Depth",
            unit="pts",
            get_cmd=":ACQ:MDEP?",
            get_parser=int,
            set_cmd=False,
        )

        self.time_scale = self.add_parameter(
            "time_scale",
            label="Time Scale",
            unit="s/div",
            get_cmd=":TIM:MAIN:SCAL?",
            get_parser=float,
            set_cmd=":TIM:MAIN:SCAL {:.9f}",
            vals=vals.Numbers(1e-9, 1000),
        )

        for ch_num in range(2):
            ch_name = f"ch{ch_num}"
            channel = MSO7054Channel(self, ch_name, ch_num)
            self.add_submodule(ch_name, channel)

    def close(self) -> None:
        self.write(":STOP")
        super().close()
