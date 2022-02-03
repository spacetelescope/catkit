import enum


from catkit.interfaces.Instrument import Instrument
import pyvisa


class ControlCodes(enum.Enum):
    MSG_START = "\x4E"
    DEFAULT_ADDRESS = "\x01"
    ADDRESS_OFFSET = "\x20"
    READ = "\x30"
    WRITE = "\x38"
    DTYPE_VMEM = "\x31"
    # The following are ascii definitions.
    SOH = "\x01"  # start of header
    STX = "\x02"  # start of text
    ETX = "\x03"  # end of text
    EOT = "\x04"  # end of transmission
    ENQ = "\x05"  # enquire
    ACK = "\x06"  # acknowledge
    NAK = "\x15"  # negative acknowledgment (comms/IO error)
    ETB = "\x17"  # end of transmission block


class AddressSpace(enum.Enum):
    """ V-memory address locations needed for header. Add offset and then convert to hex. The following are octal addresses as listed
        in the user manual. """
    DEFAULT_ADDRESS = 0o0000
    OFFSET = 0o0001  # Added to each address below.
    INITIALIZATION_FLAG = 0o40602  # Bits 0-3 correspond to devices 0-4 respectively. (1 := must be initialized, 0 := ready)
    MOTION_FLAG = 0o40601  # Bits 16-20. Bit 16 := status for all 4 devices. Bits 17-20 correspond to devices 0-4 respectively. (1 := moving, 0 := not moving).
    ERROR_FLAG = 0o40600  # Bit 8 (1 := error, 0 := OK)
    INCREMENT_POSITION_BITS = 0o40600  # Bits 0-3 correspond to devices 0-4 respectively. To initialize device or increment position set bit to 1.
    # The following are for READ to obtain current positions and data is only valid if the device has been initialized.
    CURRENT_POSITION_DEV_1 = 0o2240
    CURRENT_POSITION_DEV_2 = 0o2241
    CURRENT_POSITION_DEV_3 = 0o2242
    CURRENT_POSITION_DEV_4 = 0o2243
    # The following are SET to move dev to relevant position. Can be used instead of INCREMENT_POSITION_BITS.
    DESTINATION_POSITION_DEV_1 = 0o2250
    DESTINATION_POSITION_DEV_2 = 0o2251
    DESTINATION_POSITION_DEV_3 = 0o2252
    DESTINATION_POSITION_DEV_4 = 0o2253


class McPherson747(Instrument):  # TODO: Write interface.

    instrument_lib = pyvisa

    BAUD_RATE = 9600
    DATA_BITS = 8
    STOP_BITS = 1
    PARITY = None
    FLOW_CONTROL = None
    ENCODING = "ascii"
    QUERY_TIMEOUT = 800  # ms
    HEADER_TIMEOUT = 20000  # ms

    def initialize(self, visa_id, timeout=1):
        self.visa_id = visa_id
        self.timeout = timeout
        self.instrument_lib = self.instrument_lib.ResourceManager("@py")
        self.timeout = max(self.QUERY_TIMEOUT, self.HEADER_TIMEOUT)  # TODO: ?
        self._name = self.__class__.__name__

    def move_device(self, device_number, position):
        ...

    def initialize_device(self, device_number):
        ...

    def check_error_flag(self):
        ...

    def get_current_position(self, device_number):
        ...

    def set_current_position(self, device_number):
        ...

    def is_moving(self, device_number=None):
        """ Bits 16-20. Bit 16 := status for all 4 devices. Bits 17-20 correspond to devices 0-4 respectively.
            (1 := moving, 0 := not moving).
        """
        # TODO: bin() is pseudo code.
        resp = bin(self._read_request(address=AddressSpace.MOTION_FLAG.value))

        any_in_motion = resp & bin(2**(16 - 1))

        if not any_in_motion:
            if device_number is None:
                return (False, False, False, False)
            else:
                in_motion = [False]*4
                base_bit = (17 - 1)
                for i in range(4):
                    in_motion[i] = resp & bin(2**(base_bit + i))

                return tuple(in_motion)

    def _open(self):

        rm = self.instrument_lib.ResourceManager('@py')

        # Open connection.
        return rm.open_resource(self.visa_id,
                                baud_rate=self.BAUD_RATE,
                                data_bits=self.DATA_BITS,
                                flow_control=self.FLOW_CONTROL,
                                parity=self.PARITY,
                                stop_bits=self.STOP_BITS,
                                encoding=self.ENCODING,
                                timeout=self.timeout,
                                # TODO: Check the following for correctness.
                                write_termination='\r',
                                read_termination='\r')

    def _close(self):
        # TODO: Do we want to set everything back to a specific state or just leave as is?
        if self.instrument:
            self.instrument.close()

    @staticmethod
    def _to_ascii_hex_pair(x):
        y = f"{x:X}"
        if len(y) % 2 != 0:
            # pad leading 0
            y = "0" + y
        return y

    @staticmethod
    def _lrc(msg):
        lrc = 0
        for byte in msg.encode("ascii"):
            lrc ^= byte
        return McPherson747._to_ascii_hex_pair(lrc)

    @staticmethod
    def _format_header(address, read):
        """
            Header format (18 bytes total):

            SOH (byte 1)
            Controller address (byte 2 & 3)
            Read or Write OP (byte 4)
            Data Type (byte 5)
            Starting Mem address MSB (byte 6 & 7)
            Starting Mem address LSB (byte 8 & 9)
            Number of complete data blocks (byte 10 & 11). A complete data block is 256 bytes.
            Number of partial data blocks (byte 12 & 13)
            Host address (byte 14 & 15)
            ETB (byte 16)
            LRC (byte 17 * 18)

            NOTE: Since only V-memory is accessed, only one 16bit data block is needed and
            therefore, the total number of complete blocks is always 0 and partial is 4 (the manufacturers refer to this
            block as a 2-byte word comprised of 4 "ASCII-bytes" where an "ASCII-byte" is 4 bits of a word).
        """
        controller_address = McPherson747._to_ascii_hex_pair(AddressSpace.DEFAULT_ADDRESS.value + AddressSpace.OFFSET.value)

        read_op = ControlCodes.READ.value if read else ControlCodes.WRITE.value

        v_memory_address = McPherson747._to_ascii_hex_pair(address.value + AddressSpace.OFFSET.value)
        starting_address_msb = v_memory_address[:2]
        starting_address_lsb = v_memory_address[2:]

        n_complete_data_blocks = "00"
        n_partial_data_blocks = "04"

        host_address = McPherson747._to_ascii_hex_pair(AddressSpace.DEFAULT_ADDRESS.value + AddressSpace.OFFSET.value)

        # NOTE: The header is sent as an ascii string.
        header = controller_address + read_op + ControlCodes.DTYPE_VMEM.value + starting_address_msb + \
                 starting_address_lsb + n_complete_data_blocks + n_partial_data_blocks + host_address

        lrc = McPherson747._lrc(header)
        return ControlCodes.SOH.value + header + ControlCodes.ETB.value + lrc

    @staticmethod
    def _format_data(data):
        """
            Data format, two byte word example :

            STX (byte 1)
            Data - ASCII byte 3 (byte 2)
            Data - ASCII byte 4 (byte 3)
            Data - ASCII byte 1 (byte 4)
            Data - ASCII byte 2 (byte 5)
            ETX (byte 6)
            LRC (byte 7 & 8)
        """

        return ControlCodes.STX.value + data[:2] + data[:2] + ControlCodes.ETX.value + McPherson747._lrc(data)

    @staticmethod
    def _parse_data(data):
        """ See _format_data(). """

        remote_lrc = data[-2:]
        host_lrc = McPherson747._lrc[data[1:5]]

        if remote_lrc != host_lrc:
            raise TypeError("Corrupt data block detected - LRCs don't match")

        return data[3:5] + data[1:3]

    def _read_data(self):
        ...
        # read data
        # check data and lrc - if they' don't match send NAK to re-request data (we'll only do this once and then raise).

    def _read_request(self, header):
        """
            1) send enquiry
            2) read acknowledgment
            3) send header
            4) read acknowledgment + data
            5) send acknowledgment
            6) read data
            7) send acknowledgment
            8) read EOT
            9) send EOT
        """
        try:
            self._enquire()
            # TODO: Will header be formatted already or should we do that here?
            self.instrument.write_ascii_values(header)
            self._read_ack()
            self._read_data()
            self._send_ACK()
            data = self._read_data()  # Steps 6 & 7
            self.read_EOT()
        finally:
            self.send_EOT()

        # parse data.
        return  McPherson747._parse_data(data)

    def _write_request(self, header):
        """
            1) send enquiry
            2) read acknowledgment
            3) send header
            4) read acknowledgment
            6) send data
            7) read acknowledgment
            6) send data
            7) read acknowledgment
            9) send EOT
        """
        try:
            self._enquire()  # Steps 1 & 2.
            # TODO: Will header be formatted already or should we do that here?
            self.instrument.write_ascii_values(header)
            self._read_ack()
            self.send_data()
            self._read_ack()
        finally:
            self.send_EOT()

    def _read_ack(self):
        resp = self.instrument.read_acii_values()
        if resp[2] == ControlCodes.ACK.value:
            return
        elif resp[2] == ControlCodes.NAK.value:
            raise IOError(f"{self._name} failed acknowledgement: NAK code received.")
        elif resp[0] == ControlCodes.EOT.value:
            # NOTE: If the 747 times out it will send back an EOT - an EOT must be sent back to continue comms.
            raise IOError(f"{self._name} unexpectedly ended transmission.")
        else:
            raise RuntimeError(f"{self._name}: Unknown error occurred whilst sending enquiry.")

    def _enquire(self):
        msg = ControlCodes.MSG_START.value + ControlCodes.ADDRESS_OFFSET.value + ControlCodes.ENQ.value
        self.instrument.query_ascii_values(msg)
        self._read_ack()

    def _send_ACK(self):
        self.instrument.write_ascii_values(ControlCodes.ACK.value)

    def send_EOT(self):
        self.instrument.write_ascii_values(ControlCodes.EOT.value)
