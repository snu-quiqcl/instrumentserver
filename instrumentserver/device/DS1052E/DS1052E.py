"""DS1052E QCoDeS Driver"""

# TODO: Add a time axis parameter and wave parameter of class ParameterWithSetPoints
# for measurements and plotting.

from __future__ import annotations

from qcodes.instrument import (
    InstrumentChannel,
    VisaInstrument,
    InstrumentBaseKWArgs,
    VisaInstrumentKWArgs,
)

from typing_extensions import Unpack


class DS1052EChannel(InstrumentChannel):
    """Class that implements a DS1052E Channel."""

    def __init__(
        self,
        parent: DS1052E,
        name: str,
        channel: int,
        **kwargs: "Unpack[InstrumentBaseKWArgs]",
    ):
        super().__init__(parent, name, **kwargs)
        self.channel = channel

        self.sample_rate = self.add_parameter(
            "sample_rate",
            label="Sample Rate",
            get_cmd=f":ACQ:SAMP? CHAN{self.channel}",
            get_parser=float,
            set_cmd=False,
        )

        self.mem_depth = self.add_parameter(
            "mem_depth",
            label="Memory Depth",
            unit="pts",
            get_cmd=f":CHAN{self.channel}:MEMD?",
            get_parser=int,
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
            get_cmd=lambda: self.parent.visa_handle.query_binary_values(
                f":WAV:DATA? CHAN{self.channel}", datatype="B"
            ),
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
                    get_cmd=f":MEAS:{key.upper()}? CHAN{self.channel}",
                    get_parser=float,
                    set_parser=False,
                ),
            )

        self.vpp = self.add_parameter(
            "vpp",
            label="VPP",
            unit="Vpp",
            get_cmd=lambda: float(self.ask(f":MEAS:VTOP? CHAN{self.channel}"))
            - float(self.ask(f":MEAS:VBAS? CHAN{self.channel}")),
            set_parser=False,
        )

        self.freq = self.add_parameter(
            "freq",
            label="FREQ",
            unit="Hz",
            get_cmd=f":MEAS:FREQ? CHAN{self.channel}",
            get_parser=float,
            set_parser=False,
        )


class DS1052E(VisaInstrument):
    """QCoDeS driver for DS1052E, an oscilloscope."""

    default_terminator = "\n"

    def __init__(
        self, name: str, address: str, **kwargs: "Unpack[VisaInstrumentKWArgs]"
    ):
        super().__init__(name, address, **kwargs)

        self.time_scale = self.add_parameter(
            "time_scale",
            label="Time Scale",
            unit="s/div",
            get_cmd=":TIM:SCAL?",
            get_parser=float,
            set_cmd=":TIM:SCAL {:.9f}",
        )

        for ch_num in range(2):
            ch_name = f"ch{ch_num}"
            channel = DS1052EChannel(self, ch_name, ch_num)
            self.add_submodule(ch_name, channel)

    def close(self) -> None:
        self.write(":STOP")
        super().close()
