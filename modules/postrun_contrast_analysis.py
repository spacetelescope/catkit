from hicat.experiments.modules import contrast_statistics

filepath = '/Users/mmaclay/hicat_data/simulations/2020-09-17T15-57-35_broadband_stroke_minimization/metrics.csv'
iteration_of_convergence = 12


contrast_statistics.calculate_confidence_interval(filepath, iteration_of_convergence=iteration_of_convergence)