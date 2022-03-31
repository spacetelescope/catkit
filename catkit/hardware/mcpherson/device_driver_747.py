import enum

from catkit.hardware.pyvisa_instrument import CommandEchoError, DEFAULT_POLL_TIMEOUT, PyVisaInstrument
import catkit.util
import pyvisa


class ControlCodes(enum.Enum):
    MSG_START = "\x4E"
    DEFAULT_ADDRESS = 0x01
    ADDRESS_OFFSET = 0x20
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
    """ V-memory address locations needed for header. Add offset and then convert to hex. The following are octal
        addresses as listed in the user manual.
    """
    DEFAULT_ADDRESS = 0o0000
    OFFSET = 0o0001  # Added to each address below.
    INITIALIZATION_FLAG = 0o40602  # Bits 0-3 correspond to devices 1-4 respectively. (1 := must be initialized, 0 := ready)
    MOTION_FLAG = 0o40601  # Bits 16-20. Bit 16 := status for all 4 devices. Bits 17-20 correspond to devices 0-4 respectively. (1 := moving, 0 := not moving).
    ERROR_FLAG = 0o40600  # Bit 8 (1 := error, 0 := OK)
    INCREMENT_POSITION_BITS = 0o40600  # Bits 0-3 correspond to devices 1-4 respectively. To initialize device or increment position set bit to 1.
    # The following are READ to obtain current positions and data is only valid if the device has been initialized.
    CURRENT_POSITION_DEV_1 = 0o2240
    CURRENT_POSITION_DEV_2 = 0o2241
    CURRENT_POSITION_DEV_3 = 0o2242
    CURRENT_POSITION_DEV_4 = 0o2243
    # The following are SET to move dev to relevant position. Can be used instead of INCREMENT_POSITION_BITS.
    DESTINATION_POSITION_DEV_1 = 0o2250
    DESTINATION_POSITION_DEV_2 = 0o2251
    DESTINATION_POSITION_DEV_3 = 0o2252
    DESTINATION_POSITION_DEV_4 = 0o2253


class McPherson747(PyVisaInstrument):

    BAUD_RATE = 9600
    DATA_BITS = 8
    STOP_BITS = pyvisa.constants.StopBits.one
    PARITY = pyvisa.constants.Parity.none
    FLOW_CONTROL = pyvisa.constants.ControlFlow.xon_xoff
    ENCODING = "ascii"
    QUERY_TIMEOUT = 800  # ms
    HEADER_TIMEOUT = 20000  # ms
    WRITE_TERMINATION = ''
    READ_TERMINATION = '\r'

    def initialize(self, visa_id, timeout=1):
        self.visa_id = visa_id
        self.timeout = timeout
        self.timeout = self.QUERY_TIMEOUT#, self.HEADER_TIMEOUT)  # TODO: ?
        self._name = self.__class__.__name__

    def _open(self):

        # rm = self.instrument_lib.ResourceManager("@py")
        # Open connection.
        self.instrument = self.instrument_lib.open_resource(self.visa_id,
                                           baud_rate=self.BAUD_RATE,
                                           data_bits=self.DATA_BITS,
                                           flow_control=self.FLOW_CONTROL,
                                           parity=self.PARITY,
                                           stop_bits=self.STOP_BITS,
                                           encoding=self.ENCODING,
                                           timeout=self.timeout,
                                           write_termination=self.WRITE_TERMINATION,
                                           read_termination=self.READ_TERMINATION)

        self.await_stop()
        return self.instrument

    def _close(self):
        if self.instrument:
            self.instrument.close()

    @staticmethod
    def lrc(msg):
        return catkit.util.to_ascii_hex_pair(catkit.util.lrc(msg))

    @staticmethod
    def format_header(address, read):
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

        address = AddressSpace(address)

        controller_address = catkit.util.to_ascii_hex_pair(AddressSpace.DEFAULT_ADDRESS.value + AddressSpace.OFFSET.value)

        read_op = ControlCodes.READ.value if read else ControlCodes.WRITE.value

        v_memory_address = catkit.util.to_ascii_hex_pair(address.value + AddressSpace.OFFSET.value)
        starting_address_msb = v_memory_address[:2]
        starting_address_lsb = v_memory_address[2:]

        n_complete_data_blocks = "00"
        n_partial_data_blocks = "04"

        host_address = catkit.util.to_ascii_hex_pair(AddressSpace.DEFAULT_ADDRESS.value + AddressSpace.OFFSET.value)

        # NOTE: The header is sent as an ascii string.
        header = controller_address + read_op + ControlCodes.DTYPE_VMEM.value + starting_address_msb + \
                 starting_address_lsb + n_complete_data_blocks + n_partial_data_blocks + host_address

        lrc = McPherson747.lrc(header)
        return ControlCodes.SOH.value + header + ControlCodes.ETB.value + lrc

    @staticmethod
    def format_data(data):
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
        if len(data) != 4:
            raise ValueError(f"Expected 4 byte data but got '{data}'")

        return ControlCodes.STX.value + data[2:4] + data[0:2] + ControlCodes.ETX.value + McPherson747.lrc(data)

    @staticmethod
    def parse_data(data):
        """ See _format_data(). """

        remote_lrc = data[-2:]
        host_lrc = McPherson747.lrc(data[1:5])

        if remote_lrc != host_lrc:
            raise TypeError("Corrupt data block detected - LRCs don't match")

        return data[3:5] + data[1:3]

    def read_request(self, address, raw=False):
        """
            1) send enquiry
            2) read acknowledgment
            3) send header
            4) read acknowledgment + data (if no full blocks, this will be the partial)
            5) send acknowledgment
            6) read data (N/A if there are no full blocks)
            7) send acknowledgment (N/A if there are no full blocks)
            8) read EOT
            9) send EOT

            NOTE: The reading of full data blocks is not implemented.
        """

        header = self.format_header(address, read=True)

        n_full_data_blocks = int(header[9:11])
        if n_full_data_blocks:
            raise NotImplementedError()

        try:
            self.enquire()
            self.instrument.write(header)
            self.read_ack()
            resp = self.instrument.read()
            self.instrument.write(ControlCodes.ACK.value)
            self.read_eot()
        finally:
            self.end_transmission()

        data = resp if raw else self.parse_data(resp)

        return data

    def write_request(self, address, data=None):
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

        header = self.format_header(address, read=False)

        n_full_data_blocks = int(header[9:11])
        if n_full_data_blocks:
            raise NotImplementedError()

        # Check data is already formatted.
        if data[0] != ControlCodes.STX.value:
            raise ValueError(f"Expected formatted date but got '{data}'")

        try:
            self.enquire()  # Steps 1 & 2.
            self.instrument.write(header)
            self.read_ack()
            self.instrument.write(data)
            self.read_ack()
        finally:
            self.end_transmission()

    def end_transmission(self):
        self.instrument.write(ControlCodes.EOT.value)
        self.read_all_bytes()

    def read_eot(self):
        resp = self.instrument.read()
        if resp != ControlCodes.EOT.value:
            raise IOError(f"Expected EOT but got '{resp}'")

    def check_ack(self, resp):
        if resp == ControlCodes.ACK.value:
            return
        elif resp == ControlCodes.NAK.value:
            raise IOError(f"{self._name} failed acknowledgement: NAK code received.")
        elif resp == ControlCodes.EOT.value:
            self.send_EOT()
            # NOTE: If the 747 times out it will send back an EOT - an EOT must be sent back to continue comms.
            raise IOError(f"{self._name} unexpectedly ended transmission.")
        else:
            raise RuntimeError(f"{self._name}: Unknown error occurred whilst sending enquiry.")

    def read_ack(self):
        resp = self.instrument.read()
        self.check_ack(resp[-1])
        return resp

    def enquire(self):
        # NOTE: The address offset and default address enum member values are hex ints.
        address = chr(ControlCodes.ADDRESS_OFFSET.value + ControlCodes.DEFAULT_ADDRESS.value)
        cmd = ControlCodes.MSG_START.value + address
        msg = cmd + ControlCodes.ENQ.value

        self.instrument.write(msg)

        resp = self.read_ack()

        echo = resp[:2]
        if echo != cmd:
            raise CommandEchoError(cmd, echo)

    def initialize_device(self, device_number):
        raise NotImplementedError()

    def is_initialized(self, device_number):
        raise NotImplementedError()

        data = self.read_request(AddressSpace.INITIALIZATION_FLAG)[-1]  # Want last byte.
        if data == 'E':  # TODO: ???????????
            return False

        # TODO: This isn't working, data from device doesn't match pattern in manual.
        return catkit.util.bit_check(ord(data), device_number) == 0

    def check_error_flag(self):
        raise NotImplementedError()

    def get_current_position(self, device_number):
        address = AddressSpace.CURRENT_POSITION_DEV_1.value + device_number - 1
        return int(self.read_request(address)[-1])

    def set_current_position(self, device_number, position, wait=True, timeout=DEFAULT_POLL_TIMEOUT):
        address = AddressSpace.DESTINATION_POSITION_DEV_1.value + device_number - 1
        data = f"000{position}"
        data = self.format_data(data)
        self.write_request(address, data)

        if wait:
            self.await_stop(timeout=timeout)

            # Check.
            current_position = self.get_current_position(device_number)
            if current_position != position:
                raise RuntimeError(f"Failed to move to desired position '{position}', still at '{current_position}'")

    def is_moving(self, device_number=None):
        """ Bits 16-20. Bit 16 := status for all 4 devices. Bits 17-20 correspond to devices 0-4 respectively.
            (1 := moving, 0 := not moving).
        """
        resp = ord(self.read_request(address=AddressSpace.MOTION_FLAG.value)[1])

        any_in_motion = bool(catkit.util.bit_check(resp, 1))

        if device_number is None or not any_in_motion:
            return any_in_motion
        else:
            return bool(catkit.util.bit_check(resp, device_number + 1))

    def await_stop(self, timeout=DEFAULT_POLL_TIMEOUT, poll_interval=0):
        """ Wait for device to indicate it has stopped moving.
        :param timeout: int, float (optional) - Raise TimeoutError if the devices hasn't stopped within timeout seconds.
                                                0, None, & negative values => infinite timeout.
        """
        catkit.util.poll_status((False,), self.is_moving, timeout=timeout, poll_interval=poll_interval)
