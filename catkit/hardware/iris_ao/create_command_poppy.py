""" Currently a dump of all poppy-related things. Will be cleaned up in later commit.
"""
import numpy as np

from catkit.config import CONFIG_INI

flat_to_flat = CONFIG_INI.getfloat('iris_ao', 'flat_to_flat')
gap_um = CONFIG_INI.getint('iris_ao', 'gap_um')


# Get number of rings of segments in pupil
pupil_sim_rings = get_num_rings()

def get_num_rings(self):
    """
    #TODO: move to poppy spot, whereever that is

    Get the number of rings of segments from number_segments_in_pupil

    This is specific for a segmented DM with 37 segments therefore:
      - 37 segments = 3 rings
      - 19 segments = 2 rings
      - 7 segments = 1 ring
      - 1 segment = 0 rings
    """
    seg_nums = np.array([37, 19, 7, 1])  # number of segments in a pupil of the corresponding # of rings
    ring_nums = np.array([3, 2, 1, 0])

    if self.number_segments_in_pupil not in seg_nums:
        raise Exception("Invalid number of segments for number_segments_in_pupil.")

    num_rings = [rings for segs, rings in zip(seg_nums, ring_nums) if self.number_segments_in_pupil == segs][0]

    return num_rings
