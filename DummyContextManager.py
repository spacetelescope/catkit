from abc import *


class DummyContextManager(object):
    __metaclass__ = ABCMeta

    def __init__(self, config_id, *args, **kwargs):
        self.config_id = config_id

    def __enter__(self, *args, **kwargs):
        print("Opened dummy context manager as a placeholder for " + self.config_id)
        return self

    def __exit__(self, type, value, traceback):
        print("Closed dummy context manager being used for " + self.config_id)
