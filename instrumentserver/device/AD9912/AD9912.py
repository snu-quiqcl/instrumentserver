from qcodes import validators as vals
from qcodes.instrument import Instrument, InstrumentModule, InstrumentBase

from instrumentserver.device.ArtyS7.ArtyS7 import ArtyS7
import numpy as np

class AD9912(InstrumentModule):

    """
    QCoDeS driver for AD9912 DDS chip
    """

    def __init__(self,
                 parent: InstrumentBase,
                 name: str,
                 board_number: int,
                 fpga: ArtyS7,
                 
                ):
        
        self.fpga = fpga
        self.board_number = board_number

        super().__init__(parent, name)

        self.channels = [1, 2]
        self.num_channels = len(self.channels)

        for ch in self.channels:
            self.add_parameter(name=f'frequency{ch}',
                               label=f'Channel {ch} Frequency',
                               unit='MHz',
                               set_parser = float, 
                               set_cmd=lambda freq, ch=ch: self._set_frequency(freq, ch),
                            #    get_cmd = False,
                               vals=vals.Numbers(10, 400))
            
            self.add_parameter(name=f'current{ch}',
                               label=f'Channel {ch} Current',
                               unit='',
                               set_cmd=lambda current, ch=ch: self._set_current(current, ch),
                            #    get_cmd = False,
                               vals=vals.Numbers(0, 1020))
            
            self.add_parameter(name=f'phase{ch}',
                               label=f'Channel {ch} Phase',
                               unit='˚',
                               set_cmd=lambda phase, ch=ch: self._set_phase(phase, ch),
                            #    get_cmd = False,
                               vals=vals.Numbers(0, 360))
            
            self.add_parameter(
                name=f'output{ch}',
                label=f'Channel {ch} Output',
                set_cmd=lambda status, ch=ch: self._set_output(status, ch),
                vals=vals.Enum('ON', 'OFF')
            )
        
    def _make_header_string(self, register_address, bytes_length, direction='W'):
        if direction == 'W':
            MSB = 0
        elif direction == 'R':
            MSB = 1
        else:
            print('Error in make_header: unknown direction (%s). ' % direction, \
                  'direction should be either \'W\' or \'R\'.' )
            raise ValueError()
            
        if type(register_address) == str:
            address = int(register_address, 16)
        elif type(register_address) == int:
            address = register_address
        else:
            print('Error in make_header: unknown register address type (%s). ' % type(register_address), \
                  'register_address should be either hexadecimal string or integer' )
            raise ValueError()
            
        if (bytes_length < 1) or (bytes_length > 8):
            print('Error in make_header: length should be between 1 and 8.' )
            raise ValueError()
        elif bytes_length < 4:
            W1W0 = bytes_length - 1
        else:
            W1W0 = 3
        
        # print(MSB, W1W0, address)
        header_value = (MSB << 15) + (W1W0 << 13) + address
        return ('%04X' % header_value)
            
    
    def _FTW_Hz(self, freq):
        # _make_header_string('0x01AB', 8)
        FTW_header = "61AB"
        y = int((2**48)*(freq/(10**9)))
        z = hex(y)[2:]
        FTW_body = (12-len(z))*"0"+z
        return FTW_header + FTW_body
    
    
    def _make_9int_list(self, hex_string, ch1, ch2):
        hex_string_length = len(hex_string)
        byte_length = (hex_string_length // 2)
        if hex_string_length % 2 != 0:
            print('Error in make_int_list: hex_string cannot be odd length')
            raise ValueError()
        
        int_list = [(ch1 << 5) + (ch2 << 4) + byte_length]
        for n in range(byte_length):
            int_list.append(int(hex_string[2*n:2*n+2], 16))
        for n in range(8-byte_length):
            int_list.append(0)
        
        return int_list
    
    def select_board(func):
        def wrapper(self, *args, **kwargs):
            self.fpga.send_command('Board' + str(self.board_number) + ' Select')
            return func(self, *args, **kwargs)
        return wrapper

    def _channel_select(self, ch):
        if ch == 1:
            ch1 = 1
            ch2 = 0

        elif ch == 2:
            ch1 = 0
            ch2 = 1

        else:
            print('Error in channel_select: channel should be either 1 or 2')
            raise ValueError()
        
        return ch1, ch2

    @select_board
    def _set_frequency(self, frequency, ch):
        ch1, ch2 = self._channel_select(ch)
        self.fpga.send_mod_BTF_int_list(self._make_9int_list(self._FTW_Hz(frequency*1e6), ch1, ch2))
        self.fpga.send_command('WRITE DDS REG')
        self.fpga.send_mod_BTF_int_list(self._make_9int_list('000501', ch1, ch2)) # Update the buffered (mirrored) registers
        self.fpga.send_command('WRITE DDS REG')

    @select_board
    def _set_current(self, current, ch):
        ch1, ch2 = self._channel_select(ch)
        self.fpga.send_mod_BTF_int_list(self._make_9int_list(self._make_header_string(0x040C, 2)+('%04x' % current), ch1, ch2)) 
        self.fpga.send_command('WRITE DDS REG')
    
    @select_board
    def _soft_reset(self, ch):
        ch1, ch2 = self._channel_select(ch)
        self.fpga.send_mod_BTF_int_list(self._make_9int_list(self._make_header_string(0, 1)+'3C', ch1, ch2))
        self.fpga.send_command('WRITE DDS REG')
        self.fpga.send_mod_BTF_int_list(self._make_9int_list(self._make_header_string(0, 1)+'18', ch1, ch2))
        self.fpga.send_command('WRITE DDS REG')
    
    @select_board
    def _set_phase(self, phase, ch):
        ch1, ch2 = self._channel_select(ch)
        # Convert phase into radian
        phase = (np.pi / 180) * phase
        # Convert phase for DDS
        phase = int(phase * (2**14) / (2 * np.pi))

        self.fpga.send_mod_BTF_int_list(self._make_9int_list(self._make_header_string(0x01AD, 2)+('%04x' % phase), ch1, ch2)) 
        self.fpga.send_command('WRITE DDS REG')
        self.fpga.send_mod_BTF_int_list(self._make_9int_list('000501', ch1, ch2)) # Update the buffered (mirrored) registers
        self.fpga.send_command('WRITE DDS REG')

    @select_board
    def _set_output(self, status, ch):
        if status == 'ON':
            header = self._make_header_string(0x0010, 1)+'90'
        elif status == 'OFF':
            header = self._make_header_string(0x0010, 1)+'91'
        else:
            print('Error in output: status should be either \'ON\' or \'OFF\'')
            raise ValueError()
        
        ch1, ch2 = self._channel_select(ch)

        self.fpga.send_mod_BTF_int_list(self._make_9int_list(header, ch1, ch2))
        self.fpga.send_command('WRITE DDS REG')


class AD9912_SIM(AD9912):

    """
    Simulated QCoDeS driver for AD9912 DDS chip
    """

    def __init__(self,
                 parent: InstrumentBase,
                 name: str,
                 board_number: int,
                ):

        super().__init__(parent, name, board_number, None)
        
        self.frequency_list = [0, 0]
        self.current_list = [0, 0]
        self.phase_list = [0, 0]
        self.output_list = ['OFF', 'OFF']

    def _channel_select(self, ch):
        if ch == 1:
            ch1 = 1
            ch2 = 0

        elif ch == 2:
            ch1 = 0
            ch2 = 1

        else:
            print('Error in channel_select: channel should be either 1 or 2')
            raise ValueError()
        
        return ch1, ch2

    def _set_frequency(self, frequency, ch):
        ch1, ch2 = self._channel_select(ch)
        self.frequency_list[ch-1] = frequency

    def _set_current(self, current, ch):
        ch1, ch2 = self._channel_select(ch)
        self.current_list[ch-1] = current
    
    def _soft_reset(self, ch):
        ch1, ch2 = self._channel_select(ch)
        self.frequency_list[ch-1] = 0
    
    def _set_phase(self, phase, ch):
        ch1, ch2 = self._channel_select(ch)
        self.phase_list[ch-1] = phase

    def _set_output(self, status, ch):
        ch1, ch2 = self._channel_select(ch)
        self.output_list[ch-1] = status


class Triple_AD9912(Instrument):

    """
    QCoDeS driver for Triple AD9912 DDS chip
    """

    def __init__(self,
                 name: str,
                 COM_port: str
                 ):
        
        try:
            self.fpga = ArtyS7('artyS7', COM_port)

        except Exception as e:
            print(f"Error in creating ArtyS7 object: {e}")
            raise ConnectionError(f"Error in creating ArtyS7 object: {e}")
        
        super().__init__(name)

        self.num_boards = 3
        self.num_channels = self.num_boards * 2

        for board_num in range(1, self.num_boards + 1):
            self.add_submodule(f"board{board_num}", AD9912(parent = self,
                                                           name = f"board{board_num}", 
                                                           board_number=board_num, 
                                                           fpga=self.fpga))
    
    def close(self):
        self.fpga.close()
        super().close()

    def get_idn(self):
        return {'vendor': 'Analog Devices',
                'model': 'AD9912'}


class Triple_AD9912_SIM(Instrument):

    """
    Simulated QCoDeS driver for Triple AD9912 DDS chip
    """

    def __init__(self,
                 name: str
                 ):
        
        super().__init__(name)

        self.num_boards = 3
        self.num_channels = self.num_boards * 2

        for board_num in range(1, self.num_boards + 1):
            self.add_submodule(f"board{board_num}", AD9912_SIM(self, f"board{board_num}", board_num))

    def get_idn(self):
        return {'vendor': 'Analog Devices',
                'model': 'AD9912',
                'firmware' : "simulated"}