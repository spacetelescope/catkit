import os
from astropy.io import fits

from hicat.wfc_algorithms import wfsc_utils


def read_dm_commands(dm_command_directory):
    """Hijacked partially from StrokeMinimization.restore_last_strokemin_dm_shapes()
    Loads a DM command from disk and returns the surface as a list."""
    surfaces = []
    for dmnum in [1, 2]:
        actuators_2d = fits.getdata(os.path.join(dm_command_directory, 'dm{}_command_2d_noflat.fits'.format(dmnum)))
        actuators_1d = actuators_2d.ravel()[wfsc_utils.dm_mask]
        actuators_1d *= 1e9  # convert from meters to nanometers # FIXME this is because of historical discrepancies, need to unify everything at some point
        surfaces.append(actuators_1d)
    return surfaces


class IrisAO():

    def __init__(self):
        self.name = 'I am a fake'

    def set_actuator(self, segnum, piston, tip, tilt):
        # This will set the segment "segnum" with a piston, tip and tilt.
        pass

    def flatten(self):
        # This will flatten the IrisAO with only the flatmap on.
        pass

    def apply_shape(self, segmented_dm_command):
        # This will apply a full segmented DM command at once.
        pass
