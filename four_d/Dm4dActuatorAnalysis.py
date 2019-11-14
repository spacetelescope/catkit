import os
import logging
from astropy.io import fits

from hicat.experiments.Experiment import Experiment
from catkit.hardware.boston.commands import poke_command, flat_command
from hicat.hardware import testbed
from catkit.hardware.FourDTechnology.Accufiz import Accufiz
from hicat.config import CONFIG_INI
import hicat.util
from catkit.catkit_types import units, quantity


class Dm4dActuatorAnalysis(Experiment):
    """
    An experiment to collect 4D images of a set of actuators poked at a set of amplitude ranges.  The resulting
    data could be used to characterize each actuator and create a precise response curve to use in the future
    as a loop table to apply more realistic commands.  Also would be useful for simulation.

    Args:
        actuators (list(int)): List of actuators to collect data for.
        amplitude_range (list(int)): List of amplitudes to iterate over.
        amplitude_range_units (pint unit): Units of amplitude range (default nanometers)
        mask (string): Name of mask file located on 4D pc.
        num_frames (int): Number of frames to take and average on the 4D
        path (string): Path to store images (default is to central store).
        filename (string): Filename override
        dm_num (int): Which DM to apply the pokes to.
        rotate (int): Amount to rotate images that are returned from 4d (increments of 90).
        fliplr (bool): Apply a flip left/right to the image returned from the 4d.
        **kwargs: Placeholder.
    """

    name = "Dm 4d Actuator Analysis"
    log = logging.getLogger(__name__)

    def __init__(self,
                 actuators=[1],
                 amplitude_range=range(100, 800, 100),
                 amplitude_range_units=units.nanometer,
                 mask="dm2_detector.mask",
                 num_frames=2,
                 output_path=None,
                 filename=None,
                 dm_num=2,
                 rotate=180,
                 fliplr=False,
                 suffix='4d',
                 **kwargs):

        super(Dm4dActuatorAnalysis, self).__init__(output_path=output_path, suffix=suffix, **kwargs)

        if filename is None:
            filename = "4d_"

        self.actuators = actuators
        self.amplitude_range = amplitude_range
        self.amplitude_range_units = amplitude_range_units
        self.mask = mask
        self.num_frames = num_frames
        self.filename = filename
        self.dm_num = dm_num
        self.rotate = rotate
        self.fliplr = fliplr
        self.kwargs = kwargs

    def experiment(self):

        with testbed.dm_controller() as dm:
            flat_command_object = flat_command(bias=True,
                                               flat_map=False,
                                               return_shortname=False,
                                               dm_num=2)
            dm.apply_shape(flat_command_object, self.dm_num)

            with Accufiz("4d_accufiz", mask=self.mask) as four_d:
                # Reference image.
                reference_path = four_d.take_measurement(path=self.output_path,
                                                         filename="reference",
                                                         rotate=self.rotate,
                                                         fliplr=self.fliplr)

                for i in self.amplitude_range:
                    file_name = "poke_amplitude_{}_nm".format(i)
                    command = poke_command(self.actuators,
                                           amplitude=quantity(i, self.amplitude_range_units), dm_num=self.dm_num)

                    dm.apply_shape(command, self.dm_num)
                    image_path = four_d.take_measurement(path=os.path.join(self.output_path, file_name),
                                                         filename=file_name,
                                                         rotate=self.rotate,
                                                         fliplr=self.fliplr)

                    # Open fits files and subtract.
                    reference = fits.getdata(reference_path)
                    image = fits.getdata(image_path)

                    # Subtract the reference from image.
                    hicat.util.write_fits(reference - image, os.path.join(self.output_path, file_name + "_subtracted"))

                    # Save the DM_Command used.
                    command.export_fits(os.path.join(self.output_path, file_name))
