import numpy as np

from hicat.config import CONFIG_INI
from hicat.hardware import testbed_state
import hicat.simulators
import zwoasi

from catkit.catkit_types import units, quantity
from catkit.interfaces.Instrument import SimInstrument
import catkit.hardware.zwo.ZwoCamera


"""SIMULATED Implementation of Hicat.Camera ABC that provides interface and context manager for using ZWO cameras."""

# Convert zwoasi module to a class such that it can be inherited.
ZwoASI = type("ZwoASI", (), zwoasi.__dict__)


class PoppyZwoEmulator(ZwoASI):
    """ Class to emulate *only our usage* of the zwoasi library. """

    implemented_camera_purposes = ("imaging_camera", "phase_retrieval_camera", "pupil_camera")#, "target_acquisition_camera")

    @classmethod
    def get_camera_mappings(cls):
        # Find all cameras
        camera_mappings = {}
        for camera_purpose in cls.implemented_camera_purposes:
            camera_config_id = CONFIG_INI.get("testbed", camera_purpose)
            camera_name = CONFIG_INI.get(camera_config_id, 'camera_name')
            camera_mappings[camera_config_id] = {"purpose": camera_purpose, "name": camera_name}
        return camera_mappings

    def __init__(self, config_id):

        self.config_id = config_id
        self.image_type = None
        self.camera_mappings = self.get_camera_mappings()

        if self.config_id not in self.camera_mappings:
            raise ValueError(f"Unknown camera for simulations: {self.config_id}")

        self.camera_purpose = self.camera_mappings[self.config_id]["purpose"]

        if self.camera_purpose == 'imaging_camera':
            hicat.simulators.optics_simulator.detector = 'imager'
            self.photometry_config_key = 'total_direct_photometry_cts_per_microsec'
        elif self.camera_purpose == 'pupil_camera':
            hicat.simulators.optics_simulator.detector = 'pupil_camera'
            self.photometry_config_key = 'total_pupil_direct_photometry_cts_per_microsec'
        elif self.camera_purpose == 'phase_retrieval_camera':
            hicat.simulators.optics_simulator.detector = 'pr_camera'
            self.photometry_config_key = 'total_prcam_direct_photometry_cts_per_microsec'
        elif self.camera_purpose == 'zernike_camera':
            hicat.simulators.optics_simulator.detector = 'zernike_wfs_camera'
            self.photometry_config_key = 'total_zernike_direct_photometry_cts_per_microsec'
        else:
            raise NotImplementedError(f"Unknown camera for simulations: {self.camera_purpose}")

    def init(self, library_file=None):
        pass

    @classmethod
    def get_num_cameras(cls):
        return len(cls.implemented_camera_purposes)

    def list_cameras(self):
        return [camera["name"] for camera in self.camera_mappings.values()]

    def Camera(self, index):
        return self

    def get_controls(self):
        # only used for oepn behavior to 
        # get / set control values to default on open
        # needs to play nicely with calls to set_controls
        # this phony dict is set to have *some* accessible value (None) for
        # every dict key we ask for
        return {'BandWidth': {'MinValue': None, 'ControlType': None, 'DefaultValue': None}}

    def set_control_value(self, control_type, value, auto=False):
        pass

    def stop_video_capture(self):
        pass

    def stop_exposure(self):
        pass

    def set_image_type(self, image_type):
        self.image_type = image_type

    def capture(self, initial_sleep, poll):
        """ Get a simulated image capture from the simulator

        :param exposure_time: exposure time in microseconds
        """
        # exposure_time == initial sleep? Who did this...
        # it looks like the og call was in seconds, does poppy want
        # microseconds? 
        #image = self.camera.capture(initial_sleep=exposure_time.to(units.second).magnitude, poll=poll.magnitude)
        exposure_time = initial_sleep.to(units.microseconds)

        # Here's the actual PSF calculation! Retrieve the simulated image from the optical system mode. This will do a
        # propagation up to the detector plane.
        self.log.info("HICAT_SIM: Simulating image capture for "+self.camera_purpose)
        image_hdulist = hicat.simulators.optics_simulator.calc_psf(apply_pipeline_binning=False)
        self.log.info("HICAT_SIM: Simulation complete for image.")
        testbed_state._simulation_latest_image = image_hdulist # Save so we can later copy some of the FITS header keywords

        counts_per_microsec = CONFIG_INI.getfloat(
            'photometry', self.photometry_config_key, fallback=90000)

        # Adjust count rate to compensate for poppy normalizing to 1.0 in entrance pupil by default.
        exit_pupil_flux_correction_factor =  CONFIG_INI.getfloat(
            'data_simulator', 'simulator_direct_exit_vs_entrance_pupil_flux')
        counts_per_microsec /= exit_pupil_flux_correction_factor

        # Apply flux normalization and exposure time scaling to the output image
        image = image_hdulist[0].data * counts_per_microsec * exposure_time

        return image.astype(np.dtype(np.int32))

    def close(self):
        pass

    def get_camera_property(self):
        # sometimes this just gets logged
        # one use where it needs keys 'MaxWidth', 'MaxHeight'
        # I *think* this can just return a dict with milquetoast values for this
        # took said milquetoast values from the __setup_control_values sim
        # function here

        return {'MaxWidth': 4096, 'MaxHeight': 4096} 
        pass

    def set_id(self):
        pass

    def set_roi(self, start_x=None, start_y=None, width=None, height=None, image_type=None):
        # sets region of interest 
        # purpose : set_roi_format, set_roi_start_position
        # set_roi_format --> _set_roi_format : 
        # check for all the errors 
        # runs zwolib.ASISetROIFormat(id_, width, height, bins, image_type)
        # set_roi_start_position --> _set_start_position :
        # runs zwolib.ASISetStartPos(id_, start_x, start_y)
        pass # according to Marshall


class ZwoCamera(SimInstrument,  catkit.hardware.zwo.ZwoCamera.ZwoCamera):
    """ Now we use poppy to take images."""

    instrument_lib = PoppyZwoEmulator

    @classmethod
    def load_asi_lib(cls):
        pass
