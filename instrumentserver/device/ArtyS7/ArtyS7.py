"""
Arty S7 QCoDeS driver for usage in QuMaRE.

Author : Minwoo Kim (Dept. of Computer Science & Engineering, SNU) myfirstexp@snu.ac.kr
"""

from qcodes import Instrument
from qcodes.instrument.parameter import Parameter
from qcodes.utils import validators as vals
import serial
import logging
import numpy as np
import importlib
from pathlib import Path
import sys
import os

from time import time

from . import SequencerProgram_v1_07 as SequencerProgram

class EscapeSequenceDetected(Exception):
    def __init__(self, escape_char):
        self.escape_char = escape_char
    def __str__(self):
        return f'\\x10{self.escape_char} is detected'
    

class ArtyS7(Instrument):
    CMD_RX_BUFFER_BYTES = 0xf
    BTF_RX_BUFFER_BYTES = 0x100
    TERMINATOR_STRING = '\r\n'
    PATTERN_BYTES = 4
    PROGRAM_MEMORY_DATA_WIDTH = 64
    PROGRAM_MEMORY_ADDR_WIDTH = 9
    MAX_OUTPUT_DATA_FIFO_TRANSMISSION_CHUNK_SIZE = 512

    EXPERIMENT_TIME_RESOLUTION = 1

    def __init__(
        self, 
        name: str, 
        serial_port: str, 
        *,
        sequencer_repo: str | os.PathLike | None = None, 
        **kwargs
    ):
        super().__init__(name, **kwargs)
        
        self.com = serial.Serial(serial_port, baudrate=57600, timeout=1,
                parity='N', bytesize=8, stopbits=2, xonxoff=False,
                rtscts=False, dsrdtr=False, writeTimeout=0)

        # Set up sequencer repository
        if sequencer_repo is None:
            # Default to a 'sequencer_programs' directory in the same location as the driver
            self.sequencer_repo = os.path.join(os.path.dirname(__file__), 'sequencer_programs')
        else:
            self.sequencer_repo = sequencer_repo
        
        # Create the repository directory if it doesn't exist
        self.sequencer_repo = Path(self.sequencer_repo).expanduser().resolve()

        # Basic Parameters
        self.add_parameter('intensity',
                   label='LED Intensity',
                   unit='',
                   get_cmd=self._read_intensity,
                   set_cmd=self._set_intensity,
                   vals=vals.Ints(0, 255),
                   docstring='Controls PWM duty cycle of status LED')

        self.add_parameter('dna',
                        label='Device DNA',
                        get_cmd=self._read_DNA,
                        docstring='Unique FPGA device identifier (56-bit)')
        
        # Validator issues for the bit pattern parameter
        '''
        self.add_parameter('bit_pattern',
                        label='Digital Output Pattern',
                        get_cmd=self._read_bit_pattern,
                        set_cmd=self._update_bit_pattern,
                        vals=vals.Lists(vals.MultiType(vals.Ints(1, 32), vals.Ints(0, 1))),
                        docstring='32-bit digital output state with mask control')
        '''

        # Program Memory Parameters - perhaps nonnecessary
        '''
        self.add_parameter('program_memory',
                   label='Program Memory',
                   get_cmd=self._read_program_memory,
                   set_cmd=self._write_program_memory,
                   vals=vals.MultiType(vals.Ints(0, (1<<9)-1), 
                                 vals.Arrays(shape=(8,))),
                    docstring='64-bit sequencer instruction memory (512 addresses)')
        '''
        
        # Sequencer Parameters
        self.add_parameter('sequencer_status',
                   label='Sequencer Execution State',
                   get_cmd=self._get_sequencer_status,
                   vals=vals.Enum('running', 'stopped'),
                   docstring='Current sequencer operation status')

        self.add_parameter('control_mode',
                        label='Sequencer Control Mode',
                        get_cmd=self._get_control_mode,
                        set_cmd=self._set_control_mode,
                        vals=vals.Enum('auto', 'manual'),
                        docstring='Sequencer execution mode: automatic or step-by-step')

        self.add_parameter('fifo_data_length',
                        label='FIFO Data Count',
                        get_cmd=self._get_fifo_data_length,
                        unit='samples',
                        docstring='Number of data points available in output FIFO')

        # Function APIs
        self.add_function('start_sequencer',
                        call_cmd=self._start_sequencer)

        self.add_function('stop_sequencer',
                        call_cmd=self._stop_sequencer)

        self.add_function('flush_fifo',
                        call_cmd=self._flush_fifo)

        self.add_function('read_fifo_data',
                        call_cmd=self._read_fifo_data,
                        args=[vals.Ints(1, 512)])

        self.add_function('check_version',
                        call_cmd=self._check_version,
                        args=[vals.Strings()])

        self.add_function('check_waveform_capture',
                        call_cmd=self._check_waveform_capture)

        self.add_function('load_program',
                        call_cmd=self._load_program,
                        args=[vals.Anything()])
        
        self.add_function('run',
                        call_cmd=self._run,
                        args=[vals.Anything()])

        # For AD9912 driver implementation
        self.add_function('send_command',
                        call_cmd=self._send_command,
                        args=[vals.Strings()])
        self.add_function('send_mod_BTF_int_list',
                        call_cmd=self._send_mod_BTF_int_list,
                        args=[vals.Lists(vals.Ints(0, 255))])

        self.connect_message()

    # Core Communication Methods
    def _send_command(self, cmd: str) -> None:
        """Send a command to the instrument."""
        if len(cmd) > self.CMD_RX_BUFFER_BYTES:
            raise ValueError(f'Command exceeds {self.CMD_RX_BUFFER_BYTES} bytes')
        
        encoded = f'!{len(cmd):x}{cmd}'.encode('latin-1').replace(b'\x10', b'\x10\x10')
        self.com.write(encoded + self.TERMINATOR_STRING.encode())

    def _send_mod_BTF_int_list(self, data: list) -> None:
        dataLength = len(data)
        if (dataLength> self.BTF_RX_BUFFER_BYTES):
            print('send_mod_BTF_int_list: Modified BTF cannot be longer than %d. Current length is %d.' \
                  % (self.BTF_RX_BUFFER_BYTES, dataLength))
        else:
            byte_count_string = '%x' % dataLength
            num_digits = len(byte_count_string)
            data_to_send = ('#%x%s' % (num_digits, byte_count_string))
            for each_byte in data:
                if each_byte == 0x10:
                    data_to_send += '\x10\x10'
                else:
                    data_to_send += chr(each_byte)
            data_to_send += '\r\n'
            data_to_send = data_to_send.encode('latin-1')
            self.com.write(data_to_send)

    def _read_next(self):
        first_char = self.com.read(1).decode('latin-1') # bytes larger than 127 cannot be translated into 'utf-8', but 'latin-1' can handle up to 255
        if first_char == '\x10':
            second_char = self.com.read(1).decode('latin-1')
            if second_char == '\x10': # '\x10\x10' is detected
                return '\x10'
            else:
                raise EscapeSequenceDetected(second_char)
        else:
            return first_char

    def _read_next_message(self) -> tuple:
        """Read next message from instrument."""
        try:
            next_char = self._read_next()
            
            if next_char == '!':
                length_of_following_data = int(self._read_next(), 16)
                data = ''
                for n in range(length_of_following_data):
                    data += self._read_next()
                    
                for n in range(len(self.TERMINATOR_STRING)):
                    next_char = self._read_next()
                    if self.TERMINATOR_STRING[n] != next_char:
                        print('read_next_message: Termination string does not match. Expected: %s, reply: %s' \
                              % (self.TERMINATOR_STRING[n], next_char))
                
                return ('!', data)
            
            elif next_char == '#':
                num_digits = int(self._read_next(), 16)
                byte_count = 0
                for n in range(num_digits):
                    byte_count = byte_count*16 + int(self._read_next(), 16)
                data = ''
                for n in range(byte_count):
                    data += self._read_next()
                    
                for n in range(len(self.TERMINATOR_STRING)):
                    next_char = self._read_next()
                    if ArtyS7.TERMINATOR_STRING[n] != next_char:
                        print('read_next_message: Termination string does not match. Expected: %s, reply: %s' \
                              % (self.TERMINATOR_STRING[n], next_char))
                
                return ('#', data)
    
            elif next_char == '':
                print('read_next_message: No more messages')
                return ('0', '')
                
            else:
                print('read_next_message: Unknown signature character: %s' % next_char)
                return ('E', next_char)
        except EscapeSequenceDetected as e:
            if e.escape_char == 'C':
                #self.log.warning('read_next_message: Escape reset ("\\x10C") is returned')
                pass
            elif e.escape_char == 'R':
                #self.log.warning('read_next_message: Escape read ("\\x10R") is returned')
                data = []
                for n in range(5):
                    data.append(ord(self._read_next()))
                for n in range(len(self.TERMINATOR_STRING)):
                    next_char = self._read_next()
                    if self.TERMINATOR_STRING[n] != next_char:
                        self.log.warning('read_next_message: Termination string of "\\x10R" does not match. Expected: %s, reply: %s' \
                              % (self.TERMINATOR_STRING[n], next_char))
                e.escape_R_data = data
            elif e.escape_char == 'W':
                #self.log.warning('read_next_message: Escape waveform ("\\x10W") is returned')
                pass

            raise e

    # Parameter Handlers
    def _read_intensity(self) -> int:
        self._send_command('READ INTENSITY')
        _, data = self._read_next_message()
        return ord(data[0])

    def _set_intensity(self, value: int) -> None:
        self.log.warning(f'Setting intensity to {value}')
        self._send_mod_BTF_int_list([value])
        self._send_command('ADJ INTENSITY')

    def _read_DNA(self) -> str:
        self._send_command('*DNA_PORT?')
        DNA_PORT = self._read_next_message()
        dna = DNA_PORT[1]
        
        # 4 MSBs show if reading from DNA_PORT is finished. If 4 MSBs == 4'h1, DNA_PORT reading is done 
        if ord(dna[0]) // 16 != 1:
            raise ValueError('Device DNA is not ready yet!')
            
        dna_val = ord(dna[0]) % 16 # Strips the 4 MSBs
        for n in dna[1:]:
            dna_val = dna_val * 256 + ord(n)
            
        return ('%015X' % dna_val) # Returns strings representing 57 bits of device DNA 

    def _update_bit_pattern(self, bits: list) -> None:
        mask = [0]*32
        values = [0]*32
        for pos, val in bits:
            mask[pos-1] = 1
            values[pos-1] = val
            
        mask_int = int(''.join(map(str, mask)), 2)
        val_int = int(''.join(map(str, values)), 2)
        
        data = [(mask_int >> i) & 0xFF for i in range(24, -8, -8)] + \
               [(val_int >> i) & 0xFF for i in range(24, -8, -8)]
               
        self._send_mod_BTF_int_list(data)
        self._send_command('UPDATE BITS')

    def _read_bit_pattern(self) -> list:
        self._send_command('READ BITS')
        _, data = self._read_next_message()
        return [(i+1, int(bit)) for i, bit in enumerate(''.join(
            format(ord(c), '08b') for c in data))]

    # Sequencer Control
    def _start_sequencer(self) -> None:
        self._send_command('START SEQUENCER')

    def _stop_sequencer(self) -> None:
        for addr in range(1 << self.PROGRAM_MEMORY_ADDR_WIDTH):
            self.load_prog(addr, [0x0f, 0, 0, 0, 0, 0, 0, 0])

    def _get_sequencer_status(self) -> str:
        reply = self._escape_read()
        if reply[0] != '\x10R':
            print('Error in sequencer_running_status: unknown type of reply (%s)' \
                  % str(reply))
            raise KeyError()
        elif (reply[2][2][0] == '0'): # Sequencer is running
            return 'running'
        elif (reply[2][2][0] == '1'): # Sequencer is not running
            return 'stopped'
        else:
            print('Error in sequencer_running_status: unknown type of reply (%s)' \
                  % str(reply))
            raise KeyError()

    def _get_control_mode(self) -> str:
        reply = self._escape_read()
        if reply[0] != '\x10R':
            print('Error in manual_control_status: unknown type of reply (%s)' \
                  % str(reply))
            raise KeyError()
        elif (reply[2][2][1] == '0'): # auto mode
            return 'auto'
        elif (reply[2][2][1] == '1'): # manual mode
            return 'manual'
        else:
            print('Error in manual_control_status: unknown type of reply (%s)' \
                  % str(reply))
            raise KeyError()

    # Program memory APIs - nonnecessary
    '''
    def _write_program_memory(self, value: tuple) -> None:
        """Enhanced program memory write with validation"""
        addr, data = value
        max_addr = (1 << self.PROGRAM_MEMORY_ADDR_WIDTH) - 1
        
        # Address validation
        if addr > max_addr:
            raise ValueError(f'Address {addr} out of range (0-{max_addr})')
            
        # Data length validation
        prog_bytes = self.PROGRAM_MEMORY_DATA_WIDTH // 8
        if len(data) != prog_bytes:
            raise ValueError(f'Requires {prog_bytes} bytes, got {len(data)}')

        addr_high = addr // 256
        addr_low = addr % 256
        
        self._send_mod_BTF_int_list([addr_high, addr_low] + data)
        self._send_command('LOAD PROG')

    def _read_program_memory(self, addr: int) -> tuple:
        """Enhanced program memory read with validation"""
        max_addr = (1 << self.PROGRAM_MEMORY_ADDR_WIDTH) - 1
        
        if addr > max_addr:
            raise ValueError(f'Address {addr} out of range (0-{max_addr})')

        addr_high = addr // 256
        addr_low = addr % 256
        
        self._send_mod_BTF_int_list([addr_high, addr_low])
        self._send_command('READ PROG')
        _, data = self._read_next_message()
        
        return (addr, [ord(c) for c in data])
    '''

    # to be used within SequencerProgram.program()
    def load_prog(self, addr: int, prog: list) -> None:
        """Direct program loading interface
        Args:
            addr: Program memory address (0-511)
            prog: 8-byte program data
        """
        max_addr = (1 << self.PROGRAM_MEMORY_ADDR_WIDTH) -1
        if addr > max_addr:
            print('%d is out of range. Address should be between 0 and %d.' % (addr, max_addr))
            return
        addr_high = addr // 256;
        addr_low = addr % 256;
        prog_bytes = self.PROGRAM_MEMORY_DATA_WIDTH/8 # 8
        if len(prog) != prog_bytes:
            print('Program bytes should be %d. %d bytes are given.' % (prog_bytes, len(prog)))
            return
        self._send_mod_BTF_int_list([addr_high, addr_low]+prog)
        self._send_command('LOAD PROG')

    # FIFO Management
    def _get_fifo_data_length(self) -> int:
        self._send_command('DATA LENGTH')
        _, data = self._read_next_message()
        return ord(data[0])*256 + ord(data[1])

    def _flush_fifo(self) -> None:
        while (length := self._get_fifo_data_length()) > 0:
            self._read_fifo_data(min(length, self.MAX_OUTPUT_DATA_FIFO_TRANSMISSION_CHUNK_SIZE))

    @staticmethod
    def convert_2bytes(byte_pair):
        return ord(byte_pair[0])*256+ord(byte_pair[1])

    def _read_fifo_data(self, length: int) -> list:
        max_chunk = self.MAX_OUTPUT_DATA_FIFO_TRANSMISSION_CHUNK_SIZE
        if length > max_chunk:
            
            length = max_chunk

        # Send read command
        self._send_mod_BTF_int_list([length//256, length%256])
        self._send_command('READ DATA')
        
        # Receive data
        msg_type, data = self._read_next_message()
        self.log.warning(f'Received {data}')
                
        # Error checking
        if msg_type != '#':
            raise ValueError(f'Invalid message type {msg_type}, expected #')
            
        expected_bytes = 8 * length
        if len(data) != expected_bytes:
            raise ValueError(f'Expected {expected_bytes} bytes, got {len(data)}')

        # Data conversion
        return [
            [
                self.convert_2bytes(data[8*n:8*n+2]),
                self.convert_2bytes(data[8*n+2:8*n+4]),
                self.convert_2bytes(data[8*n+4:8*n+6]),
                self.convert_2bytes(data[8*n+6:8*n+8])
            ] for n in range(length)
        ]

    def _escape_read(self) -> dict:
        self.com.write(b'\x10R') # Read bits
        try:
            self._read_next_message()
        except EscapeSequenceDetected as e:
            if e.escape_char != 'R':
                raise e
            else:
                raw_data = e.escape_R_data
                data = []
                for n in range(4):
                    data.append(format(raw_data[n], '08b'))
                status_bits = format(raw_data[4], '08b')
                return ('\x10R', status_bits, data)

    def _check_version(self, version: str) -> None:
        self._send_command('*IDN?')
        _, data = self._read_next_message()
        if data != version:
            raise ValueError(f'FPGA version mismatch: {data} != {version}')

    def _check_waveform_capture(self) -> str:
        self.com.write(b'\x10R') # Read bits
        try:
            self._read_next_message()
        except EscapeSequenceDetected as e:
            if e.escape_char != 'R':
                raise e
            else:
                waveform_capture_info = (e.escape_R_data)[4]
                if (waveform_capture_info & (1<<2)) == 0:
                    status_string = 'No capture_waveform_data module is implemented!'
                else:
                    status_string = ''
                    if (waveform_capture_info & (1<<1)) > 0:
                        status_string += 'Trigger is armed. '
                    if (waveform_capture_info & (1<<0)) > 0:
                        status_string += 'Captured waveform data exists. '
                    if (waveform_capture_info & 3) == 0:
                        status_string += 'No waveform data exists. '
        print(status_string)

    def _set_control_mode(self, mode: str) -> None:
        if mode == 'auto':
            self._send_command('AUTO MODE')
        elif mode == 'manual':
            self._send_command('MANUAL MODE')
        else:
            raise ValueError(f'Invalid mode {mode}')
        
        # Consume the ack so the buffer is empty
        self._read_next_message()

    # Load the SequencerProgram
    # s.program()
    def _load_program(self, s : SequencerProgram):
        try:
            # Stop sequencer if running
            if self._get_sequencer_status() == 'running':
                self._stop_sequencer()
            
            # Clear old data
            self._flush_fifo()

            # Upload program
            s.program(show=False, target=self)
            self._send_command('AUTO MODE')

        except Exception as e:
            raise

    def _resolve_program_path(self, user_path: str | os.PathLike) -> Path:
        """
        Return absolute Path of `user_path`.
        * absolute input → returned unchanged
        * relative input → interpreted relative to self.program_repo
        """
        p = Path(user_path)
        return p if p.is_absolute() else (self.sequencer_repo / p).resolve()

    def _run(self, path : str) -> list:
        '''
        runs a SequencerProgram at the path and returns the entire FIFO
        path : Absolute path

        # Notes on the sequencerProgram
        The sequencer program code must include a function load_sequencer_program that takes a SequencerProgram instance as a parameter.
        The role of the function is to load the commands on to the SequencerProgram instance s.
        '''
        full_path = self._resolve_program_path(path)

        spec = importlib.util.spec_from_file_location("SequencerCode", full_path)
        if spec is None or spec.loader is None:
            raise FileNotFoundError(full_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        s = SequencerProgram.SequencerProgram()
        s = module.load_sequencer_program(s)
        
        self._load_program(s)
        self._start_sequencer()

        while self._get_sequencer_status() == 'running':
            time.sleep(self.EXPERIMENT_TIME_RESOLUTION)
        
        if (self._get_sequencer_status() == 'stopped' and self._get_fifo_data_length() > 0):
            fifo_data_count = self._get_fifo_data_length()
            data = self._read_fifo_data(fifo_data_count)

        return data


    def get_idn(self) -> dict:
        self._send_command('*IDN?')
        _, data = self._read_next_message()
        parts = (data.split(',') + [None] * 4)[:4]
        return {
            'vendor': parts[0],
            'model': parts[1],
            'serial': parts[2],
            'firmware': parts[3]
        }

    def close(self) -> None:
        self.com.close()
        super().close()