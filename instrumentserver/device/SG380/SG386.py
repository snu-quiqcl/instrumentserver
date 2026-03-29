"""Example usage of and notes about the SG386 RF signal generator.

While it is possible to use the provided QCoDeS SG384 driver, it may be necessary to
modify the existing driver. Because SG386 does not return values of parameters that
haven't been enabled, such as rear offset clock voltage, but rather raises an error,
the driver should be updated to check if the dependent options are on before
requesting these values. The modification is recommended to avoid timeout errors when
adding the instrument to a QCoDeS station.
"""

# Example usage:

import qcodes
from qcodes.instrument_drivers.stanford_research.SG384 import SG384


if __name__ == "__main__":
    # Change the oscilloscope address to the actual address before testing.
    instrument_address = "TCPIP::133.41.1.174::INSTR"
    sg386 = SG384(name="sg386", address=instrument_address)

    station = qcodes.Station()
    station.add_component(sg386)

    print("Instrument Identity:", sg386.get_idn())

    sg386.frequency(1e6) # 1 MHz
    print("Frequency:", sg386.frequency(), "Hz")

    sg386.amplitude_LF(-45)
    print("Amplitude:", sg386.amplitude_LF(), "dBm")

    sg386.close()