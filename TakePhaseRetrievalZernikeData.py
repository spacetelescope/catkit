from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
import os

from .Experiment import Experiment
from ..hicat_types import quantity, units, MetaDataEntry, FpmPosition
from .modules.phase_retrieval import take_phase_retrieval_data
from .. import util
from ..hardware.boston import DmCommand


class TakePhaseRetrievalData(Experiment):
    name = "Take Phase Retrieval Zernike Data"

    def __init__(self,
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=5,
                 step=10,
                 path=None,
                 camera_type="phase_retrieval_camera",
                 position_list=None,
                 **kwargs):
        """
        Takes a set of data with the phase_retrieval camera (default) at constant "step" increments from focus.
        :param bias: (boolean) Apply a constant bias on the DM.
        :param flat_map: (boolean) Apply the flat map onto the DM.
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
        self.kwargs = kwargs

    def experiment(self):
        if self.path is None:
            self.path = util.create_data_path(suffix="phase_retrieval_zernike")

        # DM1 Flat, DM2 Astigmatism45_40nm with 0 defocus.
        astig45_command_path = "z:/Testbeds/hicat_dev/data_vault/dm2_calibration/2018-01-21T12-07-16_4d_zernike_loop_astigmatism_45/40_nm_p2v/Astigmatism 45_zernike_volts_dm2.fits"

        take_phase_retrieval_data(self.exposure_time,
                                  self.num_exposures,
                                  self.step,
                                  os.path.join(self.path, "astigmatism"),
                                  self.camera_type,
                                  position_list=self.position_list,
                                  dm2_command=DmCommand.load_dm_command(astig45_command_path),
                                  **self.kwargs)


