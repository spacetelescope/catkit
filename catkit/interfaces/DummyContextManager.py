import logging


class DummyContextManager(object):

    log = logging.getLogger()

    def __init__(self, config_id):
        self.config_id = config_id

    def __enter__(self, *args, **kwargs):
        self.log.info("Opened dummy context manager as a placeholder for " + self.config_id)
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        self.log.info("Closed dummy context manager being used for " + self.config_id)
