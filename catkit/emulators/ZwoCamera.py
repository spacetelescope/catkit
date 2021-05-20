import abc
import logging

import zwoasi
from catkit.config import CONFIG_INI

import catkit.hardware.zwo.ZwoCamera


# Convert zwoasi module to a class such that it can be inherited.
ZwoASI = type("ZwoASI", (), zwoasi.__dict__)


class ZwoEmulator(ZwoASI):
    """ Class to emulate of the zwoasi library. """

    implemented_camera_purposes = None

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
        self.log = logging.getLogger()

        self.config_id = config_id
        self.image_type = None
        self.control_values = {}

        self.camera_mappings = self.get_camera_mappings()
        if self.config_id not in self.camera_mappings:
            raise ValueError(f"Unknown camera for simulations: {self.config_id}")

        self.camera_purpose = self.camera_mappings[self.config_id]["purpose"]

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

    def start_video_capture(self):
        pass

    def stop_video_capture(self):
        pass

    def stop_exposure(self):
        pass

    def set_image_type(self, image_type):
        self.image_type = image_type

    @abc.abstractmethod
    def capture(self, initial_sleep=0.01, poll=0.01, buffer=None, filename=None):
        pass

    def capture_video_frame(self, buffer=None, filename=None, timeout=None):
        return self.capture(buffer=buffer, filename=filename)

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

