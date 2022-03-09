import ctypes

c_void_p = ctypes.POINTER(ctypes.c_void_p)
c_int_p = ctypes.POINTER(ctypes.c_int)
c_double_p = ctypes.POINTER(ctypes.c_double)


class TSP01Emulator(ctypes.Structure):

    _fields_ = [("serial_number", ctypes.c_char_p),
                ("temp", ctypes.c_double),
                ("humidity", ctypes.c_double)]

    def __init__(self, serial_number, temp, humidity):
        self.serial_number = serial_number.encode()
        self.temp = temp
        self.humidity = humidity

    def TLTSPB_init(self, device_name, id_query, reset_device, connection):
        # int TLTSPB_init(char * device_name, bool id_query, bool reset_device, void ** connection)

        connection_p = ctypes.cast(connection, c_void_p)  # deref ctypes.byref()
        connection_p.contents.value = ctypes.addressof(self)

        # NOTE: E.g., ``self.temp`` is accessible via:
        # TSP01Emulator_p = ctypes.POINTER(TSP01Emulator)
        # new_self = ctypes.cast(connection, TSP01Emulator_p).contents
        # new_self.temp

        return 0

    @staticmethod
    def TLTSPB_close(connection):
        # int TLTSPB_close(void * connection)
        return 0

    def TLTSPB_measTemperature(self, connection, channel, temp):
        # int TLTSPB_getTemperatureData(void * connection, int channel, double * temp)

        pointer = ctypes.cast(temp, c_double_p)  # deref ctypes.byref()
        pointer.contents.value = self.temp
        return 0

    def TLTSPB_measHumidity(self, connection, humidity):
        # int TLTSPB_getHumidityData(void * connection, ?, double * humidity)

        pointer = ctypes.cast(humidity, c_double_p)  # deref ctypes.byref()
        pointer.contents.value = self.humidity
        return 0

    @staticmethod
    def TLTSPB_errorMessage(connection, status_code, error_message):
        # int TLTSPB_errorMessage(void * connection, int status_code, char * error_message)

        error_message.value = "Error".encode()
        return 0

    @staticmethod
    def TLTSPB_findRsrc(connection, device_count):
        # int TLTSPB_findRsrc(void * connection, int * device_count)

        pointer = ctypes.cast(device_count, c_int_p)  # deref ctypes.byref()
        pointer.contents.value = 1
        return 0

    def TLTSPB_getRsrcName(self, connection, device_index, buffer):
        # int TLTSPB_getRsrcName(void * connection, int device_index, char * buffer)

        buffer.value = self.serial_number
        return 0
