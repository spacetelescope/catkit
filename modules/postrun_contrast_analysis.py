from hicat.experiments.modules import contrast_statistics
'''
Quick Launcher to be run after a strokemin run. This allows users to specify a convergence iteration and generate
separate plots. Include these plots in the science slides.

runfolder: type=str, the name of the run's folder eg. 2020-07-15T17-27-04_broadband_stroke_minimization
iteration_of_convergence, type=int, the iteration after which the contrast appears to have converged.
'''

runfolder = ""
iteration_of_convergence = 15
if len(runfolder) > 0:
    filepath = str("C:/Users/HICAT/hicat_data/"+str(runfolder)+"/metrics.csv")
    contrast_statistics.calculate_confidence_interval(filepath, iteration_of_convergence=iteration_of_convergence)
