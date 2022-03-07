import enum
import time

from catkit.interfaces.FilterWheel import FilterWheel
import usb


class Report(enum.Enum):
    GET_FILTER = bytearray([0, 0])
    SET_FILTER = bytearray([0, 0])


class StandardUSBFilterWheel(FilterWheel):

    instrument_lib = usb
    ENDPOINT = 0x81
    N_BYTES = 2
    MIN_FILTER = 1

    def initialize(self, idVendor=0x1278, idProduct=0x0920, timeout=8*1000):
        self.idVendor = idVendor
        self.idProduct = idProduct
        self.timeout = timeout

        self.max_filters = None

    def _open(self):
        self.instrument = usb.core.find(idVendor=self.idVendor, idProduct=self.idProduct)

        if self.instrument is None:
            raise RuntimeError(f"Device not found (idVendor: {self.idVendor}, idProduct: {self.idProduct}).")

        self.instrument.set_configuration()

        self.max_filters = self.get_max_filters()

        return self.instrument

    @property
    def filter(self):
        return self.get_position()

    @filter.setter
    def filter(self, value):
        self.set_position(value)

    def _close(self):
        ...

    def get_max_filters(self):
        self.hid_set_report(Report.GET_FILTER.value)
        return self.read()[1]

    def get_position(self):
        filter_number = 0
        while filter_number == 0:  # 0 := in motion.
            self.hid_set_report(Report.GET_FILTER)
            filter_number = self.read()[0]
        return filter_number

    def set_position(self, new_position):
        if self.MIN_FILTER < new_position > self.max_filters:
            raise ValueError(f"Filter number must be in the range {self.MIN_FILTER}-{self.max_filters}")

        filter_number = 0
        while filter_number == 0:  # 0 := in motion.
            report = Report.SET_FILTER.value
            report[0] = new_position
            self.hid_set_report(report)
            filter_number = self.read()[0]
        return filter_number

    def hid_set_report(self, report):
        self.instrument.ctrl_transfer(0x21,    # REQUEST_TYPE_CLASS | RECIPIENT_INTERFACE | ENDPOINT_OUT
                                      9,       # SET_REPORT
                                      0x200,   # "Vendor" Descriptor Type + 0 Descriptor Index
                                      0,       # USB interface.
                                      report)  # the HID payload as a byte array

    def read(self):
        resp = self.instrument.read(self.ENDPOINT, self.N_BYTES, self.timeout)
        return resp[0], resp[1]
