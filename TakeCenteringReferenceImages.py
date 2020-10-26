import os
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import astropy.io.fits as fits

from catkit.catkit_types import ImageCentering, units, quantity
from catkit.hardware.boston.commands import flat_command
from hicat.experiments.Experiment import Experiment
from hicat.experiments.modules.general import take_exposures
from hicat.hardware import testbed_state
from hicat.hardware.testbed import move_filter
from hicat.config import CONFIG_INI


class TakeCenteringReferenceImages(Experiment):
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

        # Pick pipeline centering method based on coronagraph mode, and if in real hardware or not
        if testbed_state.simulation:
            # In simulated mode, we will create perfectly centered images by construction
            # This involves overriding whatever's currently in the config to disable WFE and jitter
            # This is not at all realistic to the hardware, intentionally.
            default_values = {}
            def override_value(key, newval):
                """ Override one value temporarily"""
                default_values[key] = CONFIG_INI.get('data_simulator', key)
                CONFIG_INI.set('data_simulator', key, str(newval))
            def un_override_values():
                """ Undo all overrides"""
                for key in default_values:
                    CONFIG_INI.set('data_simulator', key, default_values[key])
            def toggle_simulator_to_reread_config():
                """ re-init simulator after a config change"""
                import hicat.simulators
                hicat.simulators.set_testbed_simulation_mode(False)
                hicat.simulators.set_testbed_simulation_mode(True)

            override_value('simulate_imaging_camera_image_jitter', False)
            override_value('power_spectrum_rms_nm', 0)
            override_value('wfe_tilt_nm', 0)
            override_value('wfe_focus_nm', 0)
            override_value('wfe_astig_nm', 0)
            override_value('wfe_coma_nm', 0)
            override_value('wfe_trefoil_nm', 0)
            toggle_simulator_to_reread_config()
            self.log.info("DISABLING simulated image jitter and WFE")

            centering_method = ImageCentering.off
            self.log.info(f'Centering method for SIMULATED {testbed_state.current_mode} is {centering_method}')
        else:
            # For the actual images on the hardware, we want to make these as precisely centered as possible, so they
            # can then serve as the references for what a centered image should look like. TBD how best to do this.
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
                       centering=centering_method,
                       **self.kwargs)


        if testbed_state.simulation:
            # if we're in simulation mode, we added overrides above.
            # Undo that here to avoid unintentional consequences for any subsequent simulated experiments.
            un_override_values()
            self.log.info("Reset simualted image jitter and WFE back to prior levels")
            toggle_simulator_to_reread_config()

        # Now make a plot to verify the centering is OK

        fig, axes = plt.subplots(figsize=(11,7), ncols=2)
        im = fits.getdata(os.path.join(self.output_path, 'coron/coron_image_cal.fits'))
        norm = matplotlib.colors.LogNorm(1, im.max() )
        cm = matplotlib.cm.get_cmap('viridis')
        cm.set_bad(cm(0))

        axes[0].imshow(im, norm=norm, cmap=cm)
        axes[0].set_title(f"New centering image for {self.color_filter}, {'Simulated' if testbed_state.simulation else 'Measured'}")

        axes[1].imshow(im, norm=norm, cmap=cm)
        axes[1].set_title(f"New centering image for {self.color_filter}, zoom to center")
        cen = (im.shape[0]-1)/2
        boxsize=10
        axes[1].set_xlim(cen-boxsize, cen+boxsize)
        axes[1].set_ylim(cen-boxsize, cen+boxsize)
        for ax in axes:
            ax.axhline(cen, ls='--',color='orange')
            ax.axvline(cen, ls='--',color='orange')
        plt.text(0.1, 0.1, self.output_path, color='gray', transform=fig.transFigure)
        plt.savefig(os.path.join(self.output_path, f"centering_reference_check_{self.color_filter}.pdf"))



if __name__ == "__main__":
    TakeCenteringReferenceImages().start()
