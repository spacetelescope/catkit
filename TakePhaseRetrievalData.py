from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from .Experiment import Experiment
from ..hicat_types import quantity, units, MetaDataEntry, FpmPosition
from .modules.phase_retrieval import take_phase_retrieval_data
from ..hardware.boston.commands import flat_command


class TakePhaseRetrievalData(Experiment):
    name = "Take Phase Retrieval Data"

    def __init__(self,
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=5,
                 step=10,
                 path=None,
                 camera_type="phase_retrieval_camera",
                 position_list=None,
                 dm1_command=flat_command(False, True, dm_num=1),
                 dm2_command=flat_command(False, True, dm_num=2),
                 suffix=None,
                 **kwargs):
        """
        Takes a set of data with the phase_retrieval camera (default) at constant "step" increments from focus.
        :param exposure_time: (pint.quantity) Pint quantity for exposure time.
        :param num_exposures: (int) Number of exposures.
        :param step: (int) Step size to use for the motor positions (default is 10).
        :param path: (string) Path to save data.
        :param camera_type: (string) Camera type, maps to the [tested] section in the ini.
        :param kwargs: Parameters for either the run_hicat_imaging function or the camera itself.
        """
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.step = step
        self.path = path
        self.camera_type = camera_type
        self.position_list = position_list
        self.dm1_command = dm1_command
        self.dm2_command = dm2_command
        self.suffix = suffix
        self.kwargs = kwargs

    def experiment(self):
        take_phase_retrieval_data(self.exposure_time,
                                  self.num_exposures,
                                  self.step,
                                  self.path,
                                  self.camera_type,
                                  position_list=self.position_list,
                                  dm1_command=self.dm1_command,
                                  dm2_command=self.dm2_command,
                                  suffix=self.suffix,
                                  **self.kwargs)


