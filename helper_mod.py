## -- IMPORTS

import struct

import usb.core
import usb.util


## -- FUNCTIONS and FIDDLING

def build_message(cmd_func, cmd_type, chan, value=None):
    """ Function to build read/write message.

    Parameters
    ----------
    cmd_func : str
        "loop", "p/i/d_gain" for what kind of adjustment.
    cmd_type : str
        "read" or "write" for whether we're writing a command or 
        reading back the value.
    chan : int
        The channel we're working on (1, 2, or 3).
    value : int/float, optional
        If writing a command should be int (for the loop) or 
        a float for the P/I/D gain. Otherwise None.

    Returns
    -------
    msg : bytes
        The message out.
    """


    # Initialize command dictionary
    cmd_dict = {'loop': 84, 'p_gain': 720, 'i_gain': 728, 'd_gain': 730}

    # Figure out address 
    addr = 11830000 + 1000*chan + cmd_dict[cmd_func]
    addr = '0x{}'.format(addr)
    addr = struct.pack('<Q', int(addr, 16))

    # Now build up the command
    if cmd_type == "read":
        if value != None:
            print('You specified a value but nothing will happen to it.')
        
        # [cmd type] [address] [number of reads] [end card]
        msg = b'\xa4' + addr[:4] + b'\x02\x00\x00\x00\x55'
    
    if cmd_type == "write":
        assert value != None, "Value is required."
        
        if cmd_func == "loop":
            assert value in [1, 0], "1 or 0 value is required for loop."

            # Convert to hex
            val = struct.pack('<I', value)

        if cmd_func in ["p_gain", "i_gain", "d_gain"]:
            
            val = struct.pack('<f', float(value))

        msg = b'\xa2', addr[:4] + val + b'\x55'

    return msg


## -- MAIN with ex

if __name__ == "__main__":
    dev = usb.core.find()
    assert dev != None, "Turn on the device you knucklehead."
    
    read_msg = build_message('loop', 'read', 1)
    cmd_msg = build_message('loop', 'write', 1, 1)

    dev.write(0x02, read_msg, 100)


    # This usually takes three tries actually?
    dev.read(0x81, 100, 1000)

