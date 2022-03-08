import enum
import time

from catkit.interfaces.FilterWheel import FilterWheel
import usb


class Report(enum.Enum):
    GET_FILTER = (0, 0)
    SET_FILTER = (1, 0)  # NOTE: 1 is a placeholder for the new filter position.


class StandardUSBFilterWheel(FilterWheel):

    instrument_lib = usb
    ENDPOINT = 0x81
    N_BYTES = 2
    MIN_POSITION = 1

    def initialize(self, idVendor=0x1278, idProduct=0x0920, timeout=8*1000):
        self.idVendor = idVendor
        self.idProduct = idProduct
        self.timeout = timeout

        self.max_position = None

    def _open(self):
        self.instrument = usb.core.find(idVendor=self.idVendor, idProduct=self.idProduct)

        if self.instrument is None:
            raise RuntimeError(f"Device not found (idVendor: {self.idVendor}, idProduct: {self.idProduct}).")

        self.instrument.set_configuration()

        self.max_position = self.get_max_filters()

        return self.instrument

    @property
    def filter(self):
        return self.get_position()

    @filter.setter
    def filter(self, value):
        self.set_position(value)

    def _close(self):
        """ Nothing to do. """
        ...

    def get_max_filters(self):
        self._hid_set_report(Report.GET_FILTER)
        return self._read()[1]

    def get_position(self):
        filter_position = 0
        while filter_position == 0:  # 0 := in motion.
            self._hid_set_report(Report.GET_FILTER)
            filter_position = self._read()[0]
            time.sleep(1)
        return filter_position

    def set_position(self, new_position):
        if self.MIN_POSITION < new_position > self.max_position:
            raise ValueError(f"Filter number must be in the range {self.MIN_POSITION}-{self.max_position}")

        report = list(Report.SET_FILTER.value)
        report[0] = new_position

        filter_position = 0
        while filter_position != new_position:
            self._hid_set_report(report)
            filter_position = self._read()[0]
            time.sleep(1)

        if filter_position != new_position:
            raise RuntimeError(f"Failed to move to position: {new_position} and remains at position: {filter_position}.")

    def _hid_set_report(self, report):
        if isinstance(report, Report):
            report = report.value

        self.instrument.ctrl_transfer(0x21,    # REQUEST_TYPE_CLASS | RECIPIENT_INTERFACE | ENDPOINT_OUT
                                      9,       # SET_REPORT
                                      0x200,   # "Vendor" Descriptor Type + 0 Descriptor Index
                                      0,       # USB interface.
                                      bytearray(report))  # the HID payload as a byte array

    def _read(self):
        resp = self.instrument.read(self.ENDPOINT, self.N_BYTES, self.timeout)
        return resp[0], resp[1]
