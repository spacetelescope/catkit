from collections import namedtuple
from .. import units

# Create a named tuple to hold metadata
MetaDataEntry = namedtuple("MetaDataEntry", "name, name_8chars, value, comment")

# Initialize State Variables.
background = False
lyot_stop = False
coronograph = False
laser_source = None
laser_value = None

# DM specific state Varibales.
sine_wave_specifications = []
bias = False
flat_map = False

def create_metadata():
    metadata = []
    metadata.append(MetaDataEntry("background", "bg", background, "Background Image"))
    metadata.append(MetaDataEntry("lyot_stop", "lyotstop", lyot_stop, "Lyot Stop"))
    metadata.append(MetaDataEntry("coronograph", "coron", coronograph, "Focal Plane Mask (coronograph)"))
    metadata.append(MetaDataEntry("laser_source", "source", laser_source, "Model of laser source"))
    metadata.append(MetaDataEntry("laser_value", "src_val", laser_value, "Laser source value (milliAmps)"))
    metadata.append(MetaDataEntry("bias", "bias", bias, "Constant voltage applied to all actuators on DM1"))
    metadata.append(MetaDataEntry("flat_map", "flat_map", flat_map, "Flat map applied to correct resting shape of DM1"))

    sine_wave_flag = False

    if sine_wave_specifications:
        sine_wave_flag = True
        metadata.append(MetaDataEntry("num_sine_waves", "nsinwave", len(sine_wave_specifications),
                                      "Number of sine waves"))

        size = len(sine_wave_specifications)
        for i, sine in enumerate(sine_wave_specifications):
            angle_string = "angle" + (str(i+1) if size > 1 else "")
            metadata.append(MetaDataEntry(angle_string, angle_string, sine.angle, "Angle of sine wave (degrees)"))

            ncycles_string = "ncycles" + (str(i+1) if size > 1 else "")
            metadata.append(MetaDataEntry(ncycles_string, ncycles_string, sine.ncycles, "Number of sine wave cycles"))

            metadata.append(MetaDataEntry(
                "peak_to_valley" + (str(i+1) if size > 1 else ""),
                "p2v" + (str(i+1) if size > 1 else ""),
                sine.peak_to_valley.to(units.nanometer).m,
                "Number of sine wave cycles"))

            phase_string = "phase" + (str(i+1) if size > 1 else "")
            metadata.append(MetaDataEntry(phase_string, phase_string, sine.phase, "Phase of sinewave (degrees)"))

    metadata.append(MetaDataEntry("sine_wave", "sinewave", sine_wave_flag,
                                  "Sine wave(s) applied to DM1 to inject speckles"))

    return metadata
