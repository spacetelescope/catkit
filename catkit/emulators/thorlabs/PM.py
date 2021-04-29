from abc import ABC, abstractmethod


class PMEmulator(ABC):
    """ Emulates the TLPM interface. """

    # int TLPM_errorMessage(void *vi, int statusCode, char description[])
    def TLPM_errorMessage(self, vi, status_code, description):
        description.value = b"Unknown error from the emulator."
        return 0

    # int TLPM_findRsrc(void *vi, int *resourceCount)
    def TLPM_findRsrc(self, vi, resource_count):
        resource_count.contents.value = self.get_num_devices()
        return 0

    # int TLPM_getRsrcName(void *vi, int device_index, char resourceName[])
    def TLPM_getRsrcName(self, vi, device_index, resource_name):
        resource_name.value = self.get_serial_number(device_index).encode()
        return 0

    # int TLPM_init(char *resourceName, bool IDQuery, bool resetDevice, void **vi)
    def TLPM_init(self, resource_name, id_query, reset_device, vi):
        self.serial_number = resource_name.decode()

        # Set vi to something that is not False.
        vi.contents.value = 1

        return 0

    # int TLPM_close(void *vi)
    def TLPM_close(self, vi):
        return 0

    # int TLPM_measPower(void *vi, double *power);
    def TLPM_measPower(self, vi, power):
        power.contents.value = self.measure_power()

    @abstractmethod
    def get_num_devices(self):
        pass

    @abstractmethod
    def get_serial_number(self, device_index):
        pass

    @abstractmethod
    def measure_power(self):
        pass
