from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

from collections import OrderedDict

# noinspection PyUnresolvedReferences
from builtins import *
import os

from .. import wolfram_wrappers
from .Experiment import Experiment
from .modules import auto_focus
from .. import calibration_take_data, calibration_util
from ..hardware.boston.flat_command import flat_command
from .. import util
from ..hicat_types import *
from ..config import CONFIG_INI


class Calibration(Experiment):
    name = "Calibration"

    def __init__(self,
                 cam_orientation=True,
                 chip_orientation=True,
                 focus=True,
                 centering=True,
                 dist_to_center=True,
                 clocking=True,
                 mtf=True,
                 write_to_csv=True,
                 path=None,
                 plot=True):

        self.write_to_csv = write_to_csv

        self.cam_orientation_step = {'process': cam_orientation}
        self.chip_orientation_step = {'process': chip_orientation}

        self.focus_step = {'process': focus}
        self.subarray_step = {'process': centering}
        self.distance_step = {'process': dist_to_center}
        self.clocking_step = {'process': clocking}
        self.mtf_step = {'process': mtf}

        self.steps = OrderedDict()
        # Order matters: Put steps in the order they need to be completed
        self.steps['camera_orientation'] = (self.cam_orientation_step, self.process_cam_orientation)
        self.steps['chip_orientation'] = (self.chip_orientation_step, self.process_chip_orientation)
        self.steps['focus'] = (self.focus_step, self.process_focus)
        self.steps['subarray_center'] = (self.subarray_step, self.process_subarray_centering)
        self.steps['distance_to_center'] = (self.distance_step, self.process_distance)
        self.steps['clocking'] = (self.clocking_step, self.process_clocking)
        self.steps['mtf'] = (self.mtf_step, self.process_mtf)

        self.flat_shape = flat_command(bias=True)
        self.cal_dict = {}
        self.outpath = path
        self.plot = plot

    def experiment(self):
        print("Calibration steps to be completed: \n")
        for step in self.steps.keys():
            if self.steps[step][0]['process']:
                print('    {}\n'.format(step))

        # Wait to set the path until the experiment starts (rather than the constructor)
        if self.outpath is None:
            local_data_path = CONFIG_INI.get("optics_lab", "local_data_path")
            cal_data_path = os.path.join(local_data_path, "calibration")
            self.outpath = util.create_data_path(initial_path=cal_data_path)

        cal_dict = self.run_steps()
        filename = 'calibration.csv'

        if cal_dict:
            if os.path.exists(filename):
                calibration_util.update_csv(cal_dict, filename)
            else:
                calibration_util.create_csv(cal_dict, filename)

    def run_steps(self):
        """
        Generic interface to initialize any and/or all defined steps.
        """
        # define list of valid steps
        for step in self.steps.keys():
            if self.steps[step][0]['process']:
                print("CALIBRATION: Calculating {} ...".format(step))
                self.steps[step][1]()
                print("CALIBRATION: Calculation of {} COMPLETE".format(step))

        return self.cal_dict

    def process_focus(self):
        focus_outpath = os.path.join(self.outpath, 'focus')
        focus_data_path = auto_focus.take_auto_focus_data(focus_outpath)
        calibration_util.collect_final_images(focus_outpath)
        output = wolfram_wrappers.run_auto_focus(focus_data_path)

        if self.write_to_csv:
            self.update_cal_dict(["best focus"], [output])

    def process_cam_orientation(self):
        cam_outpath = os.path.join(self.outpath, 'double_sin')
        calibration_take_data.run_speckle_experiment(cam_outpath)
        calibration_util.collect_final_images(cam_outpath, "*sin_noxterm.fits")

    def process_chip_orientation(self):
        data, subarray_x, subarray_y = calibration_take_data.recenter_subarray(outpath=None, plot=self.plot)

    def process_subarray_centering(self):
        subarray_outpath = os.path.join(self.outpath, 'subarray')
        self.data, subarray_x, subarray_y = calibration_take_data.recenter_subarray(outpath=subarray_outpath)

        if self.write_to_csv:
            self.update_cal_dict(["subarray center x", "subarray center y"], [subarray_x, subarray_y])

    def process_distance(self):
        try:
            data = self.data
        except NameError:
            data = calibration_take_data.take_cal_data(FpmPosition.coron, self.flat_shape, 1,
                                                       quantity(1, units.millisecond), num_exposures=5)
        centroid, coords = calibration_util.find_center(data, coron=True, return_coords=True)
        dist = calibration_util.find_average_distance_to_center(centroid, coords)

        if self.write_to_csv:
            self.update_cal_dict(["average distance to center [pixels]"], [dist])

    def process_clocking(self):
        data = calibration_take_data.take_cal_data(FpmPosition.coron, self.flat_shape, 1,
                                                   quantity(1, units.millisecond), num_exposures=5)

        mean_angle_hori, mean_angle_vert, mean_angle = calibration_util.find_clocking_angles(data[0])
        # mean_err_hori, mean_err_vert, err_angle = find_clocking_angles(sim)

        if self.write_to_csv:
            self.update_cal_dict(["clocking horizontal", "clocking vertical", "clocking angle"],
                                 [mean_angle_hori, mean_angle_vert, mean_angle])

    def process_mtf(self):
        mtf_data_path = calibration_take_data.take_mtf_data(self.outpath)
        output = wolfram_wrappers.run_mtf(mtf_data_path)
        ps_wo_focus, ps_w_focus, focus = output.split(",")

        if self.write_to_csv:
            self.update_cal_dict(["MTF: plate scale, no focus", "MTF: plate scale, focus", "MTF: focus"],
                                 [ps_wo_focus, ps_w_focus, focus])

    def update_cal_dict(self, names, values):
        for name, value in zip(names, values):
            self.cal_dict[name] = value
