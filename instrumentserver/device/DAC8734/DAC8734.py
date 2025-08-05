"""DAC8734 QCoDeS Driver"""

from qcodes.instrument import (
    Instrument,
    InstrumentBaseKWArgs,
    find_or_create_instrument,
)

from typing_extensions import Unpack

from ..ArtyS7.ArtyS7 import ArtyS7


class DAC8734(Instrument):
    """QCoDeS driver for DAC8734

    At initialization, the driver attempts to find an ArtyS7 QCoDeS Instrument instance
    by the given name. If failed, it creates a new instance with the given com_port.
    """

    def __init__(
        self,
        name: str,
        fpga_name: str,
        com_port: str,
        **kwargs: "Unpack[InstrumentBaseKWArgs]",
    ):
        super().__init__(name, **kwargs)
        self.fpga = find_or_create_instrument(ArtyS7, fpga_name, com_port)

        for i in range(0, 16):
            self.add_parameter(f"v{i}", unit="V", get_cmd=None, set_cmd=None, initial_value=0)

    def load_dac(self) -> None:
        self.fpga.send_command("LDAC")

    def update_ldac_period(self, clock_count: int) -> None:
        if clock_count > 255:
            raise ValueError(
                "Error in update_ldac_period: clock_count should be less than 256"
            )
        self.fpga.send_mod_BTF_int_list([clock_count])
        self.fpga.send_command("LDAC LENGTH")

    def update(self) -> None:
        for i in range(0, 2):
            for j in range(0, 8):
                dac_number, ch = 2 * i + j % 2, j // 2
                self.update_voltage_register(
                    dac_number, ch, getattr(self, f"v{8 * i + j}")()
                )

    def update_voltage_register(
        self,
        dac_number: int,
        ch: int,
        voltage: float,
        bipolar: bool = True,
        v_ref: int = 7.5,
    ) -> None:
        code = int(65536 / (4 * v_ref) * voltage)
        if bipolar:
            if -32768 < code < 32767:
                raise ValueError(
                    f"Error in voltage_out (dac_number: {dac_number}, ch: {ch}): \
                    Voltage is out of range."
                )
            code = (code + 65536) % 65536
        else:
            if voltage < 0:
                raise ValueError(
                    f"Error in voltage_out (dac_number: {dac_number}, ch: {ch}): \
                    Voltage cannot be negative with unipolar setting."
                )
            elif voltage > 17.5:
                raise ValueError(
                    f"Error in voltage_out (dac_number: {dac_number}, ch: {ch}): \
                    Voltage cannot be larger than 17.5 V"
                )

            if code > 65535:
                raise ValueError(
                    f"Error in voltage_out (dac_number: {dac_number}, ch: {ch}): \
                    Voltage is out of range."
                )

        message = [1 << dac_number, 0x04 + ch, code // 256, code % 256]
        self.fpga.send_mod_BTF_int_list(message)
        self.fpga.send_command("WRITE REG")

    # def set_ch0_a1_a2_a3(self, voltage, bipolar=True, v_ref=7.5):
    #     self.voltage_register_update(0, 1, voltage, bipolar, v_ref)
    #     self.voltage_register_update(0, 2, voltage, bipolar, v_ref)
    #     self.voltage_register_update(0, 3, voltage, bipolar, v_ref)
    #     self.load_dac()

    # def set_123(self, ch, voltage, bipolar=False, v_ref=7.5):
    #     self.voltage_register_update(ch, 1, voltage, bipolar, v_ref)
    #     self.voltage_register_update(ch, 2, voltage, bipolar, v_ref)
    #     self.voltage_register_update(ch, 3, voltage, bipolar, v_ref)
    #     self.load_dac()

    # def init_dac(self):
    #     for i in range(0, 16):
    #         getattr(self, f"v{i}")(0)
    #     self.update()

    # def trap_EC(self):
    #     self.v0(1)
    #     self.v1(1)
    #     self.v2(-2)
    #     self.v3(-2)
    #     self.v4(1)
    #     self.v5(1)
    #     self.v6(0)
    #     self.v7(2)
    #     self.v8(2)
    #     self.v9(-1)
    #     self.v10(-1)
    #     self.v11(2)
    #     self.v12(2)
    #     self.v13(0)
    #     self.v14(0.772)
    #     self.v15(0.406)
    #     self.update()

    # def test_EC(self):
    #     self.v0(1)
    #     self.v1(1)
    #     self.v2(-1)
    #     self.v3(-1)
    #     self.v4(1)
    #     self.v5(1)
    #     self.v6(0)
    #     self.v7(1.5)
    #     self.v8(1.5)
    #     self.v9(-0.5)
    #     self.v10(-0.5)
    #     self.v11(1.5)
    #     self.v12(1.5)
    #     self.v13(0)
    #     self.v14(0.925)
    #     self.v15(0.479)
    #     self.update()

    # def manyions(self):
    #     self.v0(0.54)
    #     self.v1(0.54)
    #     self.v2(-0.86)
    #     self.v3(-0.86)
    #     self.v4(0.58)
    #     self.v5(0.58)
    #     self.v6(0)
    #     self.v7(0.54)
    #     self.v8(0.54)
    #     self.v9(-0.86)
    #     self.v10(-0.86)
    #     self.v11(0.54)
    #     self.v12(0.54)
    #     self.v13(0)
    #     self.v14(0.188)
    #     self.v15(0.08)
    #     self.update()

    # def fiveions(self):
    #     self.v0(-0.1)
    #     self.v1(-0.1)
    #     self.v2(-4.06)
    #     self.v3(-4.06)
    #     self.v4(-0.1)
    #     self.v5(-0.1)
    #     self.v6(0)
    #     self.v7(3.76)
    #     self.v8(3.76)
    #     self.v9(-0.2)
    #     self.v10(-0.2)
    #     self.v11(3.76)
    #     self.v12(3.76)
    #     self.v13(0)
    #     self.v14(2.138)
    #     self.v15(-1.1)
    #     self.update()

    # def sym_pos(self):
    #     self.v14(self.v14() + 0.02)
    #     self.v15(self.v15 + 0.02)
    #     self.update()

    # def sym_neg(self):
    #     self.v14(self.v14() - 0.02)
    #     self.v15(self.v15 - 0.02)
    #     self.update()

    # def asym_pos(self):
    #     self.v14(self.v14() + 0.02)
    #     self.v15(self.v15 - 0.02)
    #     self.update()

    # def asym_neg(self):
    #     self.v14(self.v14() - 0.02)
    #     self.v15(self.v15 + 0.02)
    #     self.update()
