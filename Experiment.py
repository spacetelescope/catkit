from abc import ABC, abstractmethod
import copy
import logging
from multiprocessing import Process
import time

from catkit.hardware.boston.commands import flat_command

from hicat.config import CONFIG_INI
import hicat.util
from hicat.experiments.SafetyTest import UpsSafetyTest, HumidityTemperatureTest, WeatherWarningTest, SafetyException
from hicat.hardware import testbed, testbed_state
from hicat.control.align_lyot import LyotStopAlignment
from hicat.control.target_acq import MotorMount, TargetAcquisition, TargetCamera


class Experiment(ABC):
    """
    Abstract base class that instills safety monitoring into any class that inherits it.  Subclasses
    need to implement a function called "experiment()", which is designated as an abstractmethod here.
    """
    name = None

    log = logging.getLogger(__name__)
    interval = CONFIG_INI.getint("safety", "check_interval")
    list_of_safety_tests = [UpsSafetyTest, HumidityTemperatureTest]#, WeatherWarningTest()]
    safety_tests =[]

    def __init__(self, output_path=None, suffix=None):
        """ Initialize attributes common to all Experiments.
        All child classes should implement their own __init__ and call this via super()

        :param output_path: Output directory to write all files to (or to subdirectories thereof).
                     For the vast majority of use cases this should be left as None, in which
                     case it will be auto-generated based on date-time + suffix.
        :paran suffix: Descriptive string to include as part of the path.
        """
        # Default is to wait to set the path until the experiment starts (rather than the constructor)
        # but users can optionally pass in a specifc path if they want to do something different in a
        # particular case.
        self.output_path = output_path
        self.suffix = suffix

        if self.safety_tests == []:
            for test in self.list_of_safety_tests:
                self.safety_tests.append(test())

    def pre_experiment(self, *args, **kwargs):
        """ This is called immediately BEFORE self.experiment()."""
        pass

    @abstractmethod
    def experiment(self, *args, **kwargs):
        """ This is where the experiment gets implemented. All child classes must implement this. """

    def post_experiment(self, *args, **kwargs):
        """ This is called immediately AFTER self.experiment()."""
        pass

    def start(self):
        """
        This function starts the experiment on a separate process and monitors power and humidity while active.
        Do not override.
        """
        experiment_process = None
        try:

            self.log.info("Running safety tests...")
            # Check tests before starting experiment.
            for safety_test in self.safety_tests:
                status, msg = safety_test.check()
                # msg may have a newline in it; if so split that into separate log messages
                for msg_line in msg.split("\n"):
                    self.log.info(msg_line)
                if not status:
                    errmessage = safety_test.name + " reports unsafe conditions. Aborting experiment before start... Details: {}".format(msg)
                    print(errmessage)
                    self.log.critical(errmessage)
                    raise SafetyException(errmessage)
            self.log.info("Safety tests passed!")

            # Initialize experiment output path. Do this here so the output path is available in the parent process
            self.init_experiment_path()

            self.log.info("Creating separate process to run experiment...")
            # Spin off and start the process to run the experiment.
            experiment_process = Process(target=self.run_experiment)
            experiment_process.start()
            self.log.info(self.name + " process started")

            while experiment_process.is_alive():

                for safety_test in self.safety_tests:
                    status, message = safety_test.check()
                    if status:
                        # Check passed, clear any warning that might be set and proceed to sleep until next iteration.
                        for msg_line in message.split("\n"):
                            self.log.info(msg_line)
                        safety_test.warning = False

                    elif safety_test.warning:
                            # Shut down the experiment (but allow context managers to exit properly).
                            errmessage = safety_test.name + " reports unsafe conditions repeatedly. Aborting experiment! Details: {}".format(msg)
                            self.log.critical(errmessage)
                            hicat.util.soft_kill(experiment_process)
                            raise SafetyException(errmessage)

                    else:
                        errmessage = (message + "\n" +  "Warning issued for " + safety_test.name +
                              ". Experiment will be softly killed if safety check fails again.")
                        self.log.warning(errmessage)
                        safety_test.warning = True

                # Sleep until it is time to check safety again.
                if not self.__smart_sleep(self.interval, experiment_process):
                    # Experiment ended before the next check interval, exit the while loop.
                    break
                    self.log.info("Experment ended before check interval; exiting.")
        except KeyboardInterrupt:
            self.log.exception("Parent process: caught ctrl-c, raising exception.")
            raise
        except SafetyException:
            self.log.exception("Safety exception.")
            raise
        except Exception as e:
            safety_exception = SafetyException("Monitoring process caught an unexpected problem: ", e)
            self.log.exception(safety_exception)
            # Shut down the experiment (but allow context managers to exit properly).
            if experiment_process is not None:
                hicat.util.soft_kill(experiment_process)
            # must return SafetyException type specifically to signal queue to stop in typical calling scripts
            raise safety_exception

    def run_experiment(self):
        """
        Wrapper for experiment to catch the softkill function's KeyboardInterrupt signal more gracefully.
        Do not override.
        """
        try:
            self.init_experiment_log()
            testbed_state.pre_experiment_return = self.pre_experiment()
            testbed_state.experiment_return = self.experiment()
            testbed_state.post_experiment_return = self.post_experiment()
        except KeyboardInterrupt:
            self.log.warning("Child process: caught ctrl-c, raising exception.")
            raise
        finally:
            testbed_state.devices.delete_all_devices()
            # Del testbed_state.cache
            keys = list(testbed_state.cache.keys())
            for key in keys:
                item = testbed_state.cache.pop(key)
                try:
                    item.__exit__(None, None, None)
                except Exception:
                    self.log.exception(f"{item} failed to exit.")

    @staticmethod
    def __smart_sleep(interval, process):
        """
        Sleep function that will return false at most 1 second after a process ends.  It sleeps in 1 second increments
        and checks if the process is alive each time.  Rather than sleeping for the entire interval.  This allows
        the master script to end when the experiment is finished.
        Do not override.

        :param interval: check_interval from ini.
        :param process: experiment process to monitor while sleeping.
        :return: True if monitoring should continue, False if the experiment is done.
        """
        sleep_count = 0
        while process.is_alive():
            time.sleep(1)
            sleep_count += 1
            if sleep_count == interval:
                return True
        return False

    def init_experiment_path(self):
        """Set up experiment output.
        Called from start() prior to experiment()

        Do not override.
        """

        if self.suffix is None:
            self.suffix = str(self.name).replace(" ","_").lower()

        if self.output_path is None:
            self.output_path = hicat.util.create_data_path(suffix=self.suffix)

    def init_experiment_log(self):
        """ Initialize log writing.
        Called from run_experiment() prior to experiment()

        Do not override.
        """

        hicat.util.setup_hicat_logging(self.output_path, self.suffix)


class HicatExperiment(Experiment, ABC):
    def pre_experiment(self, *args, **kwargs):

        # The device cache should be and needs to be empty.
        if testbed_state.devices:
            raise Exception(f"The device cache (testbed_state.devices) is NOT empty and contains the following keys: {testbed_state.devices.keys()}")

        # Instantiate, open connections, and cache all required devices.
        try:
            with testbed.laser_source() as laser, \
                    testbed.dm_controller() as dm, \
                    testbed.motor_controller() as motor_controller, \
                    testbed.apodizer_picomotor_mount() as apodizer_picomotor_mount, \
                    testbed.quadcell_picomotor_mount() as quadcell_picomotor_mount, \
                    testbed.beam_dump() as beam_dump, \
                    testbed.imaging_camera() as cam, \
                    testbed.pupil_camera() as pupilcam, \
                    testbed.zwfs_camera() as zwfscam, \
                    testbed.temp_sensor(config_id="aux_temperature_sensor") as temp_sensor, \
                    testbed.target_acquisition_camera() as ta_cam, \
                    testbed.color_wheel() as color_wheel, \
                    testbed.nd_wheel() as nd_wheel:

                devices = {'laser': laser,
                           'dm': dm,
                           'motor_controller': motor_controller,
                           'beam_dump': beam_dump,
                           'imaging_camera': cam,
                           'pupil_camera': pupilcam,
                           'zwfs_camera': zwfscam,
                           'temp_sensor': temp_sensor,
                           'color_wheel': color_wheel,
                           'nd_wheel': nd_wheel}

                # Cache Lyot stop alignment devices in testbed_state.
                ls_align_devices = {'motor_controller': motor_controller, 'pupil_camera': pupilcam}

                # Cache target-acquisition devices in testbed_state.
                ta_devices = {"picomotors": {MotorMount.APODIZER: apodizer_picomotor_mount,
                                             MotorMount.QUAD_CELL: quadcell_picomotor_mount},
                              "beam_dump": beam_dump,
                              "cameras": {TargetCamera.SCI: cam,
                                          TargetCamera.TA: ta_cam}}

                # Add devices to cache.
                testbed_state.devices.update(ls_align_devices, namespace="ls_align_devices")
                testbed_state.devices.update(ta_devices, namespace="ta_devices")
                testbed_state.devices.update(devices)
                # -----------------
                # CODE FREE ZONE
                # -----------------
        except Exception:
            # WARNING!!! Adding devices to the cache will persist them beyond the with block thus any exception raised
            # between the cache set and the end of the with block will result in devices NOT safely closing!
            # Explicitly close all devices in this eventuality.
            testbed_state.devices.delete_all_devices()
            raise
        # Exit the with block early so as to test persistence sooner rather than later.

        # Flatten DMs before attempting initial target acquisition or Lyot alignment.
        dm_flat = flat_command(bias=False, flat_map=True)
        devices["dm"].apply_shape_to_both(dm_flat, copy.deepcopy(dm_flat))

        # Align the Lyot Stop
        if self.align_lyot_stop:
            lyot_stop_controller = LyotStopAlignment(ls_align_devices,
                                                     output_path_root=self.output_path,
                                                     calculate_pixel_scale=True)
            lyot_stop_controller.iterative_align_lyot_stop()

        # Run Target Acquisition.
        with TargetAcquisition(ta_devices,
                               self.output_path,
                               use_closed_loop=False,
                               n_exposures=20,
                               exposure_period=5,
                               target_pixel_tolerance={TargetCamera.TA: 2, TargetCamera.SCI: 25}) as ta_controller:
            testbed_state.cache["ta_controller"] = ta_controller

            # Now setup filter wheels.
            testbed.move_filter(wavelength=640,
                                nd="clear_1",
                                devices={"color_wheel": devices["color_wheel"], "nd_wheel": devices["nd_wheel"]})
            if self.run_ta:
                ta_controller.acquire_target(recover_from_coarse_misalignment=True)
            else:
                # Plot position of PSF centroid on TA camera.
                ta_controller.distance_to_target(TargetCamera.TA, check_threshold=False)
