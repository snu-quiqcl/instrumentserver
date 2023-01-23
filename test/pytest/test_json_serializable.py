import qcodes as qc

from instrumentserver.blueprints import (bluePrintFromInstrumentModule,
                                         bluePrintFromMethod,
                                         bluePrintFromParameter,
                                         bluePrintToDict,
                                         from_dict,
                                         ParameterBroadcastBluePrint,
                                         )
from instrumentserver.testing.dummy_instruments.generic import DummyInstrumentWithSubmodule
from instrumentserver.testing.dummy_instruments.rf import ResonatorResponse


class CustomParameter(qc.Parameter):

    def __int__(self, name, *args, **kwargs):
        """
        Well lets see if you go anywhere
        """
        super().__init__(name, *args, **kwargs)
        self.value = 0

    def get_raw(self):
        return self.value

    def set_raw(self, val):
        self.value = val
        return self.value


class MyClass:

    def customFunction(self, x: int, y:int) -> int:
        print(f'I am in my function')
        return x*y


def test_basic_param_dictionary():
    my_param = CustomParameter(name='my_param', unit='M')
    param_bp = bluePrintFromParameter('', my_param)
    bp_dict = bluePrintToDict(param_bp)
    reconstructed_bp = from_dict(bp_dict)
    assert param_bp == reconstructed_bp


def test_basic_function_dictionary():
    my_method = MyClass.customFunction
    method_bp = bluePrintFromMethod("", my_method)
    bp_dict = bluePrintToDict(method_bp)
    reconstructed_bp = from_dict(bp_dict)
    assert method_bp == reconstructed_bp


def test_basic_instrument_dictionary():
    my_rr = ResonatorResponse('rr')
    instrument_bp = bluePrintFromInstrumentModule("", my_rr)
    bp_dict = bluePrintToDict(instrument_bp)
    reconstructed_bp = from_dict(bp_dict)
    assert instrument_bp == reconstructed_bp

    my_dummy = DummyInstrumentWithSubmodule('dummy')
    dummy_bp = bluePrintFromInstrumentModule("", my_dummy)
    dummy_bp_dict = bluePrintToDict(dummy_bp)
    reconstructed_dummy_bp = from_dict(dummy_bp_dict)
    assert dummy_bp == reconstructed_dummy_bp

def test_basic_broadcast_parameter_dictionary():
    broadcast_bp = ParameterBroadcastBluePrint(name='my_param', action='an_action', value=-56, unit='M')
    bp_dict = bluePrintToDict(broadcast_bp)
    reconstructed_bp = from_dict(bp_dict)
    assert broadcast_bp == reconstructed_bp