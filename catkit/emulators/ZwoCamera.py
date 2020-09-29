import copy
import logging

import numpy as np

import zwoasi

from hicat.config import CONFIG_INI
from hicat.hardware import testbed_state
import hicat.simulators

from catkit.interfaces.Instrument import SimInstrument
import catkit.hardware.zwo.ZwoCamera


"""SIMULATED Implementation of Hicat.Camera ABC that provides interface and context manager for using ZWO cameras."""

# Convert zwoasi module to a class such that it can be inherited.
ZwoASI = type("ZwoASI", (), zwoasi.__dict__)


class PoppyZwoEmulator(ZwoASI):
    """ Class to emulate *only our usage* of the zwoasi library. """

    implemented_camera_purposes = ("imaging_camera",
                                   "phase_retrieval_camera",
                                   "pupil_camera",
                                   "target_acquisition_camera")

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
        self.log = logging.getLogger(__name__)

        self.config_id = config_id
        self.image_type = None
        self.control_values = {}
        self.camera_mappings = self.get_camera_mappings()
        self.photometry_config_key = None

        if self.config_id not in self.camera_mappings:
            raise ValueError(f"Unknown camera for simulations: {self.config_id}")

        self.camera_purpose = self.camera_mappings[self.config_id]["purpose"]

        # helper function for repetitive config flag retrieval:
        def get_camera_config_flag(label):
            return CONFIG_INI.getboolean('data_simulator',
                                         f'simulate_{self.camera_purpose}_{label}',
                                         fallback=False)

        self.simulate_background = get_camera_config_flag('background')
        self.simulate_photon_noise = get_camera_config_flag('photon_noise')
        self.simulate_read_noise = get_camera_config_flag('read_noise')
        self.simulate_image_jitter = get_camera_config_flag('image_jitter')
        self.simulate_readout_quantization = get_camera_config_flag('readout_quantization')

        self.simulate_background_rate = CONFIG_INI.getfloat('data_simulator',
                                                            f'simulate_{self.camera_purpose}_background_counts_per_microsec',
                                                            fallback=0.0)
        self.simulate_jitter_sigma = CONFIG_INI.getfloat('data_simulator',
                                                         f'simulate_{self.camera_purpose}_jitter_sigma_pixels',
                                                         fallback=0.0)
        if self.simulate_photon_noise or self.simulate_read_noise:
            gain_db = CONFIG_INI.getint(self.config_id, 'gain')
            if gain_db != 0:
                raise NotImplementedError(
                    "SimZwoCamera noise model does not yet support camera gain settings other than 0 db")
            else:
                # Values from https://astronomy-imaging-camera.com/manuals/ASI178%20Manual%20EN.pdf section 5 plots
                self.gain_e_per_count = 0.9 / 4  # electrons/ADU, from ZWO documentation for ASI178.
                self.readnoise_counts = 2.2 * 4  # readnoise in ADU
                # Note, factor of 4 is for 14 bit readout into 16 bits, skipping lowest 2 bits
        else:
            self.gain_e_per_count = self.readnoise_counts = 0

        self.log.info(f"Simulated {self.camera_purpose} noise model: Background {self.simulate_background}; "
                      f"photon noise {self.simulate_photon_noise}, gain {self.gain_e_per_count} e-/count; "
                      f"read noise {self.simulate_read_noise}, {self.readnoise_counts} counts; "
                      f"jitter {self.simulate_image_jitter}, {self.simulate_jitter_sigma} pixels")
        self._reuse_cached_psf_prior_to_adding_noise = False

    def init(self, library_file=None):
        pass

    @classmethod
    def get_num_cameras(cls):
        return len(cls.implemented_camera_purposes)

    def list_cameras(self):
        return [camera["name"] for camera in self.camera_mappings.values()]

    def Camera(self, id_):
        return self

    def get_controls(self):
        # only used for oepn behavior to 
        # get / set control values to default on open
        # needs to play nicely with calls to set_controls
        # this phony dict is set to have *some* accessible value (None) for
        # every dict key we ask for
        return {'BandWidth': {'MinValue': None, 'ControlType': None, 'DefaultValue': None}}

    def set_control_value(self, control_type, value, auto=False):
        accepted_types = (int,)
        if value is not None and not isinstance(value, accepted_types):
            raise ValueError(f"Expected type {accepted_types} got '{type(value)}'")
        self.control_values[control_type] = value

    def stop_video_capture(self):
        pass

    def stop_exposure(self):
        pass

    def set_image_type(self, image_type):
        self.image_type = image_type

    def capture(self, initial_sleep=0.01, poll=0.01, buffer=None, filename=None):
        """ Get a simulated image capture from the simulator """
        if self.camera_purpose == 'imaging_camera':
            hicat.simulators.optics_simulator.detector = 'imager'
            self.photometry_config_key = 'total_direct_photometry_cts_per_microsec'
        elif self.camera_purpose == 'target_acquisition_camera':
            # TODO: Simulate the actual TA camera rather than using imaging camera.
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

        # Here's the actual PSF calculation! Retrieve the simulated image from the optical system mode. This will do a
        # propagation up to the detector plane.
        if self._reuse_cached_psf_prior_to_adding_noise:
            self.log.info("HICAT_SIM: Reusing cached prior sim; adding independent noise realization.")
            image_hdulist = copy.deepcopy(testbed_state._simulation_latest_image)
        else:
            image_hdulist = hicat.simulators.optics_simulator.calc_psf(apply_pipeline_binning=False)
            self.log.info("HICAT_SIM: Simulation complete for image.")
            testbed_state._simulation_latest_image = image_hdulist  # Save so we can later copy some of the FITS header keywords
            # or reuse, for efficient simulation of multiple exposures

        counts_per_microsec = CONFIG_INI.getfloat('photometry', self.photometry_config_key, fallback=90000)

        # Adjust count rate to compensate for poppy normalizing to 1.0 in entrance pupil by default.
        exit_pupil_flux_correction_factor =  CONFIG_INI.getfloat('data_simulator', 'simulator_direct_exit_vs_entrance_pupil_flux')
        counts_per_microsec /= exit_pupil_flux_correction_factor

        # Apply flux normalization and exposure time scaling to the output image
        exposure_time = self.control_values[self.ASI_EXPOSURE]
        image = image_hdulist[0].data * counts_per_microsec * exposure_time

        ### Noise Simulations (Optional)
        # Noise terms may be turned on or off individually using config settings.
        sim_zwo_random_state = np.random.RandomState()

        if self.simulate_background:
            image += self.simulate_background_rate * exposure_time
        if self.simulate_photon_noise:
            image = sim_zwo_random_state.poisson(image * self.gain_e_per_count) / self.gain_e_per_count
        if self.simulate_read_noise:
            image += sim_zwo_random_state.randn(*image.shape) * self.readnoise_counts
        if self.simulate_image_jitter:
            # Simulate image jitter. For now just with integer pixel shifts so this is fast.
            # FIXME get actual statistics on what the jitter is. This is a complete handwave!
            shift_vec = sim_zwo_random_state.normal(self.simulate_jitter_sigma, size=2).round().astype(int)

        image = hicat.cross_correlation.roll_image(image, shift_vec)

        if self.simulate_readout_quantization:
            # Note, this camera writes 14 bits readout into 16, leaving the lowest two bits always 0, such that the minimum step is 4 counts
            # Simulate camera saturation: clip maximum value to the largest possible 16 bit unsigned number
            image = np.clip(image.astype(np.int32), a_min=0, a_max=(2 ** 16 - 1))

            # Simulate quantization. i.e. the last two bits are always 0. Simulate this by bitwise masking out last two bits here
            image = image.astype(np.int32) & ~np.int32(1) & ~np.int32(2)

        # cast return to float32, consistent with cast for ZwoCamera
        return image.astype(np.float32)

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

    def set_id(self, id, id_str):
        pass

    def set_roi(self, start_x=None, start_y=None, width=None, height=None, bins=None, image_type=None):
        # sets region of interest
        # purpose : set_roi_format, set_roi_start_position
        # set_roi_format --> _set_roi_format : 
        # check for all the errors 
        # runs zwolib.ASISetROIFormat(id_, width, height, bins, image_type)
        # set_roi_start_position --> _set_start_position :
        # runs zwolib.ASISetStartPos(id_, start_x, start_y)
        pass  # according to Marshall


class ZwoCamera(SimInstrument,  catkit.hardware.zwo.ZwoCamera.ZwoCamera):
    """ Now we use poppy to take images."""

    instrument_lib = PoppyZwoEmulator

    @classmethod
    def load_asi_lib(cls):
        pass
