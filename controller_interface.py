## -- IMPORTS

import logging
import struct
import time
import warning

import usb.core
import usb.util


## -- FUNCTIONS and FIDDLING


class Controller:

    """Controller connection class. 

    This Controller class acts as a useful connection and storage vehicle 
    for commands sent to the controller. It has built in functions that 
    allow for writing commands, checking the status, etc. By instantiating
    the Controller object you find the connected usb controller and set
    the default configuration. Memory managers in the back end should
    close the connection when the time is right.

    """

    
    def __init__(self):

        """ Initial function to find device, set the config, make sure 
        it exists, and start a record of the command history."""

        self.dev = usb.core.find()
        if self.dev == None:
            raise Error("Go get the device sorted you knucklehead.")
        self.dev.set_configuration()
        self.history = {}

    def check_config(self):
        """Checks the feasible configurations for the device."""
        
        for cfg in self.dev:
            print(cfg)
        
    def build_message(self, cmd_key, cmd_type, chan, value=None):
        """Builds the message to send to the controller. The messages
        must be 10 or 6 bytes, in significance increasing order -- which 
        for some godawful reason means backwards but sorted into bytes. 

        The format of the message to write to a new location is :
        [1 byte type (0xA2)] [4 byte address] [4 byte int/first half of float] 
        [1 byte sign off (0x55)]
        
        To write something else to the same location :
        [1 byte type (0xA3)] [4 byte message (second half of float)] 
        [1 byte sign off]

        To read from a location : 
        [1 byte type (0xA4)] [4 byte address] [4 byte numReads][1 byte sign off]
        
        Parameters
        ----------
        cmd_key : str
            The key to point toward the p/i/d_gain or loop.
        cmd_type : str  
            Either "read" to read a message or "write" to write a command.
        chan : int
            1 or 2 for which channel.
        value : int/float, optional
            If it's writing a command, what value to set it to. This 
            will fail if it needs a value and is not given one.

        Returns
        -------
        message : array of bytes
            An array of bytes messages. One if it's a simple read/write, 
            or two if it needs to write a float and use two messages.
        """
        
        cmd_dict = {'loop': 84, 'p_gain': 720, 'i_gain': 728, 'd_gain': 730}

        addr = 11830000 + 1000*chan + cmd_dict[cmd_key]
        addr = '0x{}'.format(addr)
        addr = struct.pack('<Q', int(addr, 16))

        # Now build message or messages 
        message = []

        if cmd_type == 'read':
            if value != None:
                warnings.warn('You specified a value but nothing will happen to it.')
            
            message.append(b'\xa4' + addr[:4] + b'\x02\x00\x00\x00\x55')

        if cmd_type == 'write':
            assert value != None, "Value is required."

            if cmd_key == 'loop':
                assert value in [1,0], "1 or 0 value is required for loop."

                # Convert to hex
                val = struct.pack('<I', value)
                message.append(b'\xa2' + addr[:4] + val + b'\x55')

            if cmd_key in ['p_gain', 'i_gain', 'd_gain']:
                
                
                # Convert to hex double (64 bit)
                val = struct.pack('<d', float(value))

                message.append(b'\xa2' + addr[:4] + val[:4] + b'\x55')
                message.append(b'\xa3' + val[4:] + b'\x55')

        
        self.history[str(time.time())] = message
        
        return message

    def send_message(self, msg):
        """Send the message to the controller.

        Parameters
        ----------
        msg : array of bytes
            A controller ready message or messages.
        """
        for message in msg:
            self.dev.write(0x02, message, 100)
        
    def read_response(self, loop, return_timer=False):
        """Read response from controller.

        Parameters
        ----------
        loop : bool
            Whether or not the command has to do with the loop, as this 
            will affect what data type we expect out of it.
        return_timer : bool, optional 
            Whether or not to return the tries and timing info.

        Returns
        -------
        value : int/float
            The int or float being sent.
        time_elapsed : float
            How long it took to read, only returned if return_timer=True.
        tries : int
            How many times it checked the message, only returned if
            return_timer=True.
        """

        resp = ''
        tries = 0
        
        
        start = time.time()
        while len(resp) < 4 and tries < 10:
            resp = self.dev.read(0x81, 100, 1000) 
            tries += 1 
        time_elapsed = time.time() - start

        addr = resp[3:7]
        address = struct.unpack('<I', addr)
        val = resp[7:-1]
        if loop:
            value = struct.unpack('<I', val[:4])
        else:
            value = struct.unpack('<d', val)
        
        if timer:
            return value, time_elapsed, tries
        else:
            return value

    def check_status(self, chan):
        """Checks the status of the loop, and p/i/d_gain for 
        the specified channel.

        Parameters
        ----------
        chan : int
            The channel to check.

        Returns
        -------
        value_dict : dict
            A dictionary with a setting for each parameter.
        """

        read_msg = {'p_gain': self.build_message('p_gain', 'read', chan),
                    'i_gain': self.build_message('i_gain', 'read', chan),
                    'd_gain': self.build_message('d_gain', 'read', chan),
                    'loop': self.build_message('loop', 'read', chan)}
        
        value_dict = {}
        print("For channel {}.".format(chan))
        for key in read_msg:
            self.send_message(read_msg[key])
            value = self.read_response(key=='loop')
            print("For parameter : {} the value is {}".format(key, value))
            value_dict[key] = value

        return value_dict 

    def command(self, cmd_key, chan, value):
        """Function to send a command to the controller and read back 
        to make sure it matches. 

        Parameters
        ----------
        cmd_key : str
            Whether to set the "loop" or "p/i/d_gain".
        chan : int
            What channel to set.
        value : int/flot
            What value to set.
        """

        write_message = self.build_message(cmd_key, "write", chan, value)
        read_message = self.build_message(cmd_key, "read", chan, value)

        self.send_message(write_message)
        self.send_message(read_message)
        set_value, time_elapsed, tries = self.read_response(cmd_key=='loop', timer=True)
        
        print('It took {} seconds and {} tries for the message to return.'.format(time_elapsed, tries))
        print(set_value, value)
        #assert set_value == value, "The value set does not match the command sent."

## -- MAIN with ex
if __name__ == "__main__":
    
    # Quick demo of doing something..
    ctrl = Controller()
    
