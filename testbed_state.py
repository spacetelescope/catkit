from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from hicat.hicat_types import MetaDataEntry, units

# Initialize State Variables.
background = None
lyot_stop = None
coronograph = None
laser_source = None
laser_value = None

# DM1 command object currently being applied.
dm1_command_object = None

# DM2 command object currently being applied.
dm2_command_object = None

# Initialize exposure background cache table.
background_cache = {}


def add_background_to_cache(time_quantity, num_exps, path):
    background_cache[(time_quantity.to(units.microsecond).m, num_exps)] = path


def check_background_cache(time_quantity, num_exps):
    key = (time_quantity.to(units.microsecond).m, num_exps)
    if key in background_cache:
        return background_cache[(time_quantity.to(units.microsecond).m, num_exps)]
    else:
        return None


def create_metadata():
    metadata = [MetaDataEntry("background", "bg", background, "Background Image"),
                MetaDataEntry("lyot_stop", "lyotstop", lyot_stop, "Lyot Stop"),
                MetaDataEntry("coronograph", "coron", coronograph, "Focal Plane Mask (coronograph)")]

    if laser_source:
        metadata.append(MetaDataEntry("laser_source", "source", laser_source, "Model of laser source"))
        metadata.append(MetaDataEntry("laser_value", "src_val", laser_value, "Laser source value (milliAmps)"))

    # Only write DM specific metadata if there is a shape applied.
    if dm1_command_object is not None:
        metadata.append(MetaDataEntry("bias_dm1", "bias_dm1", dm1_command_object.bias,
                                      "Constant voltage applied to actuators on DM1"))
        metadata.append(MetaDataEntry("flat_map_dm1", "flatmap1", dm1_command_object.flat_map,
                                      "Flat map applied to correct shape of DM1"))

        sin_flag = True if dm1_command_object.sin_specification else False
        metadata.append(MetaDataEntry("sine_wave_dm1", "sine_dm1", sin_flag,
                                      "Sine wave(s) applied to DM1 to inject speckles"))

        # Write the sine wave meta data for DM1.
        if dm1_command_object.sin_specification is not None:
            metadata.append(MetaDataEntry("num_sine_waves_dm1", "nsin_dm1", len(dm1_command_object.sin_specification),
                                          "Number of sine waves on DM1"))

            size = len(dm1_command_object.sin_specification)
            for i, sine in enumerate(dm1_command_object.sin_specification):
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

    if dm2_command_object is not None:
        metadata.append(MetaDataEntry("bias_dm2", "bias_dm2", dm2_command_object.bias,
                                      "Constant voltage applied to actuators on DM2"))
        metadata.append(MetaDataEntry("flat_map_dm2", "flatmap1", dm2_command_object.flat_map,
                                      "Flat map applied to correct shape of DM2"))

        sin_flag = True if dm2_command_object.sin_specification else False
        metadata.append(MetaDataEntry("sine_wave_dm2", "sine_dm2", sin_flag,
                                      "Sine wave(s) applied to DM2 to inject speckles"))

        # Write the sine wave meta data for DM2.
        if dm2_command_object.sin_specification is not None:
            metadata.append(MetaDataEntry("num_sine_waves_dm2", "nsin_dm2", len(dm2_command_object.sin_specification),
                                          "Number of sine waves on DM2"))

            size = len(dm2_command_object.sin_specification)
            for i, sine in enumerate(dm2_command_object.sin_specification):
                metadata.append(MetaDataEntry("angle" + (str(i + 1) if size > 1 else "") + "_dm2",
                                              "rot" + (str(i + 1) if size > 1 else "") + "_dm2",
                                              sine.angle,
                                              "Angle of DM2 sine wave (degrees)"))

                metadata.append(MetaDataEntry("ncycles" + (str(i + 1) if size > 1 else "") + "_dm2",
                                              "ncyc" + (str(i + 1) if size > 1 else "") + "dm2",
                                              sine.ncycles,
                                              "Number of sine wave cycles on DM2"))

                metadata.append(MetaDataEntry("peak_to_valley" + (str(i + 1) if size > 1 else "") + "_dm2",
                                              "p2v" + (str(i + 1) if size > 1 else "") + "_dm2",
                                              sine.peak_to_valley.to(units.nanometer).m,
                                              "Number of sine wave cycles on DM2"))

                metadata.append(MetaDataEntry("phase" + (str(i + 1) if size > 1 else "") + "_dm2",
                                              "phase" + (str(i + 1) if size > 1 else "") + "_2",
                                              sine.phase,
                                              "Phase of sinewave (degrees) on DM2"))

    return metadata
