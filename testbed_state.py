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

# DM1 specific state Varibales.
sine_wave_specifications_dm1 = []
bias_dm1 = False
flat_map_dm1 = False

# DM2 specific state Varibales.
sine_wave_specifications_dm2 = []
bias_dm2 = False
flat_map_dm2 = False


def create_metadata():
    metadata = []
    metadata.append(MetaDataEntry("background", "bg", background, "Background Image"))
    metadata.append(MetaDataEntry("lyot_stop", "lyotstop", lyot_stop, "Lyot Stop"))
    metadata.append(MetaDataEntry("coronograph", "coron", coronograph, "Focal Plane Mask (coronograph)"))

    if laser_source:
        metadata.append(MetaDataEntry("laser_source", "source", laser_source, "Model of laser source"))
        metadata.append(MetaDataEntry("laser_value", "src_val", laser_value, "Laser source value (milliAmps)"))


    # Only write DM specific metadata if there is a shape applied.
    if sine_wave_specifications_dm1 or bias_dm1 or flat_map_dm1:
        metadata.append(MetaDataEntry("bias_dm1", "bias_dm1", bias_dm1,
                                      "Constant voltage applied to actuators on DM1"))
        metadata.append(MetaDataEntry("flat_map_dm1", "flatmap1", flat_map_dm1,
                                      "Flat map applied to correct shape of DM1"))

        sin_flag = True if sine_wave_specifications_dm1 else False
        metadata.append(MetaDataEntry("sine_wave_dm1", "sine_dm1", sin_flag,
                                      "Sine wave(s) applied to DM1 to inject speckles"))

    if sine_wave_specifications_dm2 or bias_dm2 or flat_map_dm2:
        metadata.append(MetaDataEntry("bias_dm2", "bias_dm2", bias_dm2,
                                      "Constant voltage applied to all actuators on DM2"))
        metadata.append(MetaDataEntry("flat_map_dm2", "flatmap1", flat_map_dm2,
                                      "Flat map applied to correct resting shape of DM2"))

        sin_flag = True if sine_wave_specifications_dm2 else False
        metadata.append(MetaDataEntry("sine_wave_dm2", "sine_dm2", sin_flag,
                                      "Sine wave(s) applied to DM2 to inject speckles"))

    # Write the sine wave meta data for DM1.
    if sine_wave_specifications_dm1:
        sine_wave_dm1_flag = True
        metadata.append(MetaDataEntry("num_sine_waves_dm1", "nsin_dm1", len(sine_wave_specifications_dm1),
                                      "Number of sine waves on DM1"))

        size = len(sine_wave_specifications_dm1)
        for i, sine in enumerate(sine_wave_specifications_dm1):
            metadata.append(MetaDataEntry("angle" + (str(i + 1) if size > 1 else "") + "_dm1",
                                          "rot" + (str(i + 1) if size > 1 else "") + "_dm1",
                                          sine.angle,
                                          "Angle of DM1 sine wave (degrees)"))

            metadata.append(MetaDataEntry("ncycles" + (str(i + 1) if size > 1 else "") + "_dm1",
                                          "ncyc" + (str(i + 1) if size > 1 else "") + "dm1",
                                          sine.ncycles,
                                          "Number of sine wave cycles on DM1"))

            metadata.append(MetaDataEntry("peak_to_valley" + (str(i + 1) if size > 1 else "") + "_dm1",
                                          "p2v" + (str(i + 1) if size > 1 else "") + "_dm1",
                                          sine.peak_to_valley.to(units.nanometer).m,
                                          "Peak to valley distance (nanometers)"))

            metadata.append(MetaDataEntry("phase" + (str(i + 1) if size > 1 else "") + "_dm1",
                                          "phase" + (str(i + 1) if size > 1 else "") + "_1",
                                          sine.phase,
                                          "Phase of sinewave (degrees) on DM1"))

    # Write the sine wave meta data for DM2.
    if sine_wave_specifications_dm2:
        sine_wave_dm2_flag = True
        metadata.append(MetaDataEntry("num_sine_waves_dm2", "nsin_dm2", len(sine_wave_specifications_dm2),
                                      "Number of sine waves on DM2"))

        size = len(sine_wave_specifications_dm2)
        for i, sine in enumerate(sine_wave_specifications_dm2):
            metadata.append(MetaDataEntry("angle" + (str(i + 1) if size > 1 else "") + "_dm2",
                                          "rot" + (str(i + 1) if size > 1 else "") + "_dm2",
                                          sine.angle,
                                          "Angle of DM2 sine wave (degrees)"))

            metadata.append(MetaDataEntry("ncycles" + (str(i + 1) if size > 1 else "") + "_dm2",
                                          "ncyc" + (str(i + 1) if size > 1 else "") + "dm2",
                                          sine.ncycles,
                                          "Number of sine wave cycles on DM2"))

            metadata.append(MetaDataEntry("peak_to_valley" + (str(i + 1) if size > 1 else "") + "_dm2",
                                          "p2v" + (str(i +1 ) if size > 1 else "") + "_dm2",
                                          sine.peak_to_valley.to(units.nanometer).m,
                                          "Number of sine wave cycles on DM2"))

            metadata.append(MetaDataEntry("phase" + (str(i + 1) if size > 1 else "") + "_dm2",
                                          "phase" + (str(i + 1) if size > 1 else "") + "_2",
                                          sine.phase,
                                          "Phase of sinewave (degrees) on DM2"))

    return metadata
