# -*- coding: utf-8 -*-

#%% Imports
import os
import argparse

from qcodes import Instrument
from instrumentserver.client import Client
from instrumentserver.serialize import saveParamsToFile
from instrumentserver.client import ProxyInstrument


def main(**kwargs):
    if 'p' in kwargs:
        port = kwargs['p']
    else: port = 'COM4'

    Instrument.close_all()
    ins_cli = Client()

    artys7 = ins_cli.find_or_create_instrument(
        name = 'artys7',
        instrument_class='instrumentserver.device.ArtyS7.ArtyS7.ArtyS7',
        serial_port = port
    )

    # Any other instruments


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Port number.")
    
    parser.add_argument("--p", type=str, help="Port")
    args = parser.parse_args()
    main(**vars(args))