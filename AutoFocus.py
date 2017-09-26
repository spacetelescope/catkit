from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
from shutil import copyfile

from ..hardware.testbed_state import MetaDataEntry
from .Experiment import Experiment
from ..hardware.boston.flat_command import flat_command
from ..hardware.testbed import *
from ..hicat_types import *
from .. import wolfram_wrappers


class AutoFocus(Experiment):
    def __init__(self,
                 bias=True,
                 flat_map=False,
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=500):
        self.bias = bias
        self.flat_map = flat_map
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures

    def __collect_final_images(self, path):
        results = [y for x in os.walk(path) for y in glob(os.path.join(x[0], "*_cal.fits"))]
        for img in results:
            copyfile(img, path)

    def experiment(self):

        # Create the date-time string to use as the experiment path.
        local_data_path = CONFIG_INI.get("optics_lab", "local_data_path")
        base_path = util.create_data_path(initial_path=local_data_path, suffix="focus")

        # Ensure flipmount is down.
        move_beam_dump(BeamDumpPosition.out_of_beam)

        # Create the motor positions for the imaging camera motor.
        position_list = np.arange(11.0, 13.7, step=.1)

        # Set exposure time.
        exposure_time = quantity(250, units.microsecond)
        num_exps = 5

        with laser_source() as laser:
            direct_laser_current = CONFIG_INI.getint("thorlabs_source_mcls1", "direct_current")
            laser.set_current(direct_laser_current)

            with dm_controller() as dm:
                dm_command_object = flat_command(bias=True)
                dm.apply_shape(dm_command_object, 1)

                for position in position_list:
                    with motor_controller() as mc:
                        mc.absolute_move("motor_img_camera", position)
                    filename = "focus_" + str(int(position * 1000))
                    metadata = MetaDataEntry("Camera Position", "CAM_POS", position * 1000, "")
                    run_hicat_imaging(exposure_time, num_exps, FpmPosition.direct, path=base_path, filename=filename,
                                      exposure_set_name="motor_" + str(int(position * 1000)), extra_metadata=metadata,
                                      raw_skip=0, use_background_cache=False)

        self.__collect_final_images(base_path)
        print(wolfram_wrappers.run_auto_focus(base_path))