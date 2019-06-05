from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
import os
from glob import glob
import logging

from .Experiment import Experiment
from ..hardware.boston.commands import flat_command
from ..hicat_types import quantity, units, MetaDataEntry, FpmPosition
from .modules.phase_retrieval import take_phase_retrieval_data
from .. import util
from ..hardware.boston import DmCommand


class TakePhaseRetrievalZernikeData(Experiment):
    name = "Take Phase Retrieval Zernike Data"
    log = logging.getLogger(__name__)

    def __init__(self,
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=5,
                 step=10,
                 output_path=None,
                 camera_type="phase_retrieval_camera",
                 position_list=None,
                 suffix="phase_retrieval_zernikes",
                 **kwargs):
        """
        Takes a set of data with the phase_retrieval camera (default) at constant "step" increments from focus.
        :param bias: (boolean) Apply a constant bias on the DM.
        :param flat_map: (boolean) Apply the flat map onto the DM.
        :param exposure_time: (pint.quantity) Pint quantity for exposure time.
        :param num_exposures: (int) Number of exposures.
        :param step: (int) Step size to use for the motor positions (default is 10).
        :param output_path: (string) Path to save data.
        :param camera_type: (string) Camera type, maps to the [tested] section in the ini.
        :param kwargs: Parameters for either the run_hicat_imaging function or the camera itself.
        """
        super(TakePhaseRetrievalZernikeData, self).__init__(output_path=output_path, suffix=suffix, **kwargs)
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.step = step
        self.camera_type = camera_type
        self.position_list = position_list
        self.kwargs = kwargs

    def experiment(self):

        # All pure zernikes at 4 different amplitudes.
        path_list = [#"z:/Testbeds/hicat_dev/data_vault/dm2_calibration/2018-01-21T15-13-01_4d_zernike_loop_spherical/",
                     "z:/Testbeds/hicat_dev/data_vault/dm2_calibration/2018-01-21T14-41-48_4d_zernike_loop_trefoilx",
                     "z:/Testbeds/hicat_dev/data_vault/dm2_calibration/2018-01-21T14-10-45_4d_zernike_loop_trefoily",
                     "z:/Testbeds/hicat_dev/data_vault/dm2_calibration/2018-01-21T13-39-31_4d_zernike_loop_comax",
                     "z:/Testbeds/hicat_dev/data_vault/dm2_calibration/2018-01-21T13-08-00_4d_zernike_loop_comay",
                     "z:/Testbeds/hicat_dev/data_vault/dm2_calibration/2018-01-21T12-37-21_4d_zernike_loop_astigmatism0",
                     "z:/Testbeds/hicat_dev/data_vault/dm2_calibration/2018-01-21T12-07-16_4d_zernike_loop_astigmatism45"]

        p2v_strings = ["20_nm_p2v", "40_nm_p2v", "80_nm_p2v", "160_nm_p2v"]
        for zernike_path in path_list:
            zernike_name = zernike_path.split("_")[-1]

            for p2v_string in p2v_strings:
                command_path = glob(os.path.join(zernike_path, p2v_string,"*.fits"))[0]
                dm2_command = DmCommand.load_dm_command(command_path, as_volts=True, dm_num=2)
                take_phase_retrieval_data(self.exposure_time,
                                          self.num_exposures,
                                          self.step,
                                          os.path.join(self.output_path, zernike_name, p2v_string),
                                          self.camera_type,
                                          position_list=self.position_list,
                                          dm1_command=flat_command(bias=False, flat_map=True, dm_num=1),
                                          dm2_command=dm2_command,
                                          **self.kwargs)
