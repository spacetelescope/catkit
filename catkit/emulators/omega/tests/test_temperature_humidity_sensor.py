from catkit.emulators.omega.iTHX_W3_2 import ITHXW32Emulator, TemperatureHumiditySensor

CONFIG_ID = "Emulated Omega Temperature Humidity Sensor"


def test_get_temperature():
    with TemperatureHumiditySensor(config_id=CONFIG_ID, host="") as sensor:
        assert(ITHXW32Emulator.NOMINAL_TEMPERATURE_C == sensor.get_temp())


def test_get_humidity():
    with TemperatureHumiditySensor(config_id=CONFIG_ID, host="") as sensor:
        assert(ITHXW32Emulator.NOMINAL_HUMIDITY == sensor.get_humidity())


def test_get_temp_humidity():
    with TemperatureHumiditySensor(config_id=CONFIG_ID, host="") as sensor:
        temperature, humidity = sensor.get_temp_humidity()
        assert(ITHXW32Emulator.NOMINAL_TEMPERATURE_C == temperature)
        assert(ITHXW32Emulator.NOMINAL_HUMIDITY == humidity)
