from collections import OrderedDict
import logging
import os
import numpy as np

from hicat import wolfram_wrappers
from hicat.experiments.Experiment import Experiment
from hicat.experiments.modules import auto_focus
from hicat import calibration_take_data, calibration_util
from catkit.hardware.boston.commands import flat_command
from catkit.catkit_types import FpmPosition, quantity, units


class Calibration(Experiment):
    name = "Calibration"
    log = logging.getLogger(__name__)


    def __init__(self,
                 cam_orientation=True,
                 chip_orientation=True,
                 focus=True,
                 centering=True,
                 dist_to_center=True,
                 clocking=True,
                 mtf=True,
                 write_to_csv=True,
                 suffix="calibration",
                 output_path=None,
                 plot=True):

        super(Calibration, self).__init__(output_path=output_path, suffix=suffix, **kwargs)

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
        self.plot = plot

    def experiment(self):
        self.log.info("Calibration steps to be completed: \n")
        for step in self.steps.keys():
            if self.steps[step][0]['process']:
                self.log.info('    {}\n'.format(step))

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
                self.log.info("CALIBRATION: Calculating {} ...".format(step))
                self.steps[step][1]()
                self.log.info("CALIBRATION: Calculation of {} COMPLETE".format(step))

        return self.cal_dict

    def process_focus(self):
        focus_outpath = os.path.join(self.output_path, 'focus')
        bias = True
        flat_map = False
        num_exposures = 200
        position_list = np.arange(10.0, 13.7, step=.1)
        exposure_time = quantity(250, units.microsecond)
        focus_data_path = auto_focus.take_auto_focus_data(bias,
                                                          flat_map,
                                                          exposure_time,
                                                          num_exposures,
                                                          position_list,
                                                          focus_outpath,
                                                          "imaging_camera")
        calibration_util.collect_final_images(focus_outpath)
        output = wolfram_wrappers.run_auto_focus(focus_data_path)

        if self.write_to_csv:
            self.update_cal_dict(["best focus"], [output])

    def process_cam_orientation(self):
        cam_outpath = os.path.join(self.output_path, 'double_sin')
        calibration_take_data.run_speckle_experiment(cam_outpath)
        calibration_util.collect_final_images(cam_outpath, "*sin_noxterm.fits")

    def process_chip_orientation(self):
        calibration_take_data.recenter_subarray(outpath=None, plot=self.plot)

    def process_subarray_centering(self):
        subarray_outpath = os.path.join(self.output_path, 'subarray')
        self.data, subarray_x, subarray_y = calibration_take_data.recenter_subarray(outpath=subarray_outpath)

        if self.write_to_csv:
            self.update_cal_dict(["subarray center x", "subarray center y"], [subarray_x, subarray_y])

    def process_distance(self):
        try:
            data = self.data
        except (NameError, AttributeError):
            data = calibration_take_data.take_cal_data(FpmPosition.coron, self.flat_shape, 1,
                                                       quantity(1, units.millisecond), num_exposures=1)[0]

        coords = calibration_util.find_psf(data, satellite_spots=True)
        centroid = calibration_util.average_satellite_spots(coords)
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
        mtf_data_path = calibration_take_data.take_mtf_data(self.output_path)
        ps_wo_focus, ps_w_focus, focus = wolfram_wrappers.run_mtf(mtf_data_path)

        if self.write_to_csv:
            self.update_cal_dict(["MTF: plate scale, no focus", "MTF: plate scale, focus", "MTF: focus"],
                                 [ps_wo_focus, ps_w_focus, focus])

    def update_cal_dict(self, names, values):
        for name, value in zip(names, values):
            self.cal_dict[name] = value
