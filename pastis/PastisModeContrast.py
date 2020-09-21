from hicat.experiments.pastis.PastisExperiment import PastisExperiment
from hicat.hardware import testbed_state


class PastisModeContrast(PastisExperiment):

    def __init__(self, pastis_modes, individual, probe_filename, dm_map_path, color_filter, nd_direct, nd_coron,
                 num_exposures, exposure_time_coron, exposure_time_direct, auto_expose, file_mode, raw_skip,
                 align_lyot_stop=True, run_ta=True):
        super().__init__(probe_filename, dm_map_path, color_filter, nd_direct, nd_coron, num_exposures,
                         exposure_time_coron, exposure_time_direct, auto_expose, file_mode, raw_skip,
                         align_lyot_stop, run_ta)

        self.pastis_modes = pastis_modes
        self.individual = individual

        self.contrast_list = []

    def experiment(self):
        # Run flux normalization
        self.log.info('Starting flux normalization')
        self.run_flux_normalization()

        # Take unaberrated direct and coro images, save normalization factor and coro_floor as attributes
        self.log.info('Measuring reference PSF (direct) and coronagraph floor')
        self.measure_coronagraph_floor()

        # Access testbed devices and set experiment path
        devices = testbed_state.devices.copy()    # TODO: Is this how I will access the IrisDM?