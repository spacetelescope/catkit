import logging

from hicat.Experiment import Experiment
from hicat.hicat_types import quantity, units, MetaDataEntry, FpmPosition
from hicat.modules.phase_retrieval import take_phase_retrieval_data
from hicat.hardware.boston.commands import flat_command


class TakePhaseRetrievalData(Experiment):
    name = "Take Phase Retrieval Data"
    log = logging.getLogger(__name__)

    def __init__(self,
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=5,
                 step=10,
                 output_path=None,
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
        :param output_path: (string) Path to save data.
        :param camera_type: (string) Camera type, maps to the [tested] section in the ini.
        :param kwargs: Parameters for either the run_hicat_imaging function or the camera itself.
        """
        super(TakePhaseRetrievalData, self).__init__(output_path=output_path, suffix=suffix, **kwargs)
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.step = step
        self.camera_type = camera_type
        self.position_list = position_list
        self.dm1_command = dm1_command
        self.dm2_command = dm2_command
        self.kwargs = kwargs

    def experiment(self):
        take_phase_retrieval_data(self.exposure_time,
                                  self.num_exposures,
                                  self.step,
                                  self.output_path,
                                  self.camera_type,
                                  position_list=self.position_list,
                                  dm1_command=self.dm1_command,
                                  dm2_command=self.dm2_command,
                                  suffix=self.suffix,
                                  **self.kwargs)
