import numpy as np

from catkit.catkit_types import ImageCentering, units, quantity
from catkit.hardware.boston.commands import flat_command
from hicat.experiments.Experiment import Experiment
from hicat.experiments.modules.general import take_exposures
from hicat.hardware import testbed_state
from hicat.hardware.testbed import move_filter


class TakeReferenceImages(Experiment):
    name = 'Take Reference Images'

    def __init__(self,
                 color_filter=640,
                 nd_filter='clear_1',
                 dm1_command_object=flat_command(bias=False, flat_map=True),
                 dm2_command_object=flat_command(bias=False, flat_map=True),
                 exposure_time=quantity(250, units.microsecond),
                 num_exposures=20,
                 camera_type="imaging_camera",
                 coronagraph=True,
                 pipeline=True,
                 exposure_set_name=None,
                 auto_expose=True,
                 **kwargs):
        """
        Take a calibrated, well centered reference image in the given wavelength filter.
        Centering method for CLC2 mode will be satellite spots, while the APLC mode will use the custom apodizer spots.
        :param color_filter: float or int, wavelength of the color filter to be used
        :param nd_filter: string, name of ND filter to be used, default "clear_1"
        :param dm1_command_object: (DmCommand) DmCommand object to apply on DM1, default flat.
        :param dm2_command_object: (DmCommand) DmCommand object to apply on DM2, default flat.
        :param exposure_time: (pint.quantity) Pint quantity for exposure time.
        :param num_exposures: (int) Number of exposures.
        :param camera_type: (string) Camera type, maps to the [tested] section in the ini, default "imaging_camera"
        :param coronagraph: bool, whether the FPM is in or not, default True
        :param pipeline: bool, whether to run the pipeline or not, default True
        :param exposure_set_name: Additional directory level (ex: coron, direct).
        :param auto_expose: bool or {catkit.catkit_types.FpmPosition: bool}, flag to enable auto exposure time correction.
        :param kwargs: Parameters for either the run_hicat_imaging function or the camera itself.
        """
        super().__init__()
        self.suffix = f'take_reference_images_{int(np.rint(color_filter))}'

        self.color_filter = color_filter
        self.nd_filter = nd_filter
        self.dm1_command_object = dm1_command_object
        self.dm2_command_object = dm2_command_object
        self.exposure_time = exposure_time
        self.num_exposures = num_exposures
        self.camera_type = camera_type
        self.coronagraph = coronagraph
        self.pipeline = pipeline
        self.exposure_set_name = exposure_set_name
        self.auto_expose = auto_expose
        self.kwargs = kwargs

    def experiment(self):

        # Pick centering method based on coronagraph mode
        if testbed_state.current_mode == 'clc2':
            centering_method = ImageCentering.satellite_spots
        if testbed_state.current_mode == 'aplc_v2':
            centering_method = ImageCentering.custom_apodizer_spots
        self.log.info(f'Centering method for {testbed_state.current_mode} is {centering_method}')

        # Set wavelength filter AND set ND filter - this assumes we use the same ND filter for the coro images in all wavelengths
        move_filter(wavelength=int(np.rint(self.color_filter)), nd=self.nd_filter)
        self.log.info(f'Moving ND filter wheel to {self.nd_filter}')
        self.log.info(f'Moving wavelength filter wheel to {int(np.rint(self.color_filter))}nm')

        # Take images and save
        take_exposures(dm1_command_object=self.dm1_command_object,
                       dm2_command_object=self.dm2_command_object,
                       exposure_time=self.exposure_time,
                       num_exposures=self.num_exposures,
                       camera_type=self.camera_type,
                       coronograph=self.coronagraph,
                       pipeline=self.pipeline,
                       path=self.output_path,
                       filename=None,
                       exposure_set_name=self.exposure_set_name,
                       suffix=self.suffix,
                       auto_expose=self.auto_expose,
                       **self.kwargs)
