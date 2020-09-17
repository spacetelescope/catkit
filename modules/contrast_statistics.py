import matplotlib.pyplot as plt
import matplotlib
import numpy as np
import pandas
import os
import logging
import glob
from scipy.optimize import curve_fit

from hicat.plotting.plot_utils import careful_savefig
import hicat.plotting.log_analysis_plots

log = logging.getLogger(__name__)

def calculate_iteration_of_convergence(filepath, slope_threshold=1E-11):
    """
    Calculate the iteration at which the contrast converges. Fits an exponential decay function, and uses the change
    to infer a slope estimate first. The absolute value of the slope must be below a set parameter, slope_threshold.
    If this fails to converge, it simply returns n/2 (iteration at the halfway point) and throws a warning.
    :param filepath: The path to the csv or df of data including iteration number and mean contrast
    :param slope_threshold: Threshold that slope must be below to be considered 'converged'
    :return: number of the iteration at which the slope *first* crosses the slope_threshold.
    """

    metrics_data = load_metrics_data(filepath)

    def func(x, a, b, c):
        return a * np.exp(-b * x) + c
    popt, pcov = curve_fit(func, metrics_data['iteration'], metrics_data['mean_image_contrast'])
    metrics_data['fit'] = func(metrics_data['iteration'], *popt)
    metrics_data['derivatives'] = metrics_data['fit'].diff()
    convergence_metrics = metrics_data[np.abs(metrics_data['derivatives']) < slope_threshold]

    # Warning fix this: selects last half of data if no convergence
    if len(convergence_metrics) == 0:
        iteration_of_convergence = int(metrics_data['iteration'].iloc[-1] / 2)
        log.warning("Iterations do not converge to required slope threshold. Selecting last half of data, iteration"
                        f" {iteration_of_convergence}.")
        warning_flag = True
    elif len(convergence_metrics) >= 1:
        iteration_of_convergence = convergence_metrics['iteration'].iloc[0]
        warning_flag = False
        log.info(f"Slope threshold reached at iteration {iteration_of_convergence}")

    return iteration_of_convergence, warning_flag


def load_metrics_data(filepath):
    """
    Returns pandas dataframe given filepath or dataframe. Adds iteration column to dataframe
    :param filepath: path to csv, or dataframe.
    :return: dataframe with iteration column
    """
    if isinstance(filepath,str):
        metrics_data = pandas.read_csv(filepath)
    elif isinstance(filepath,pandas.DataFrame):
        metrics_data = filepath

    if 'iteration' not in metrics_data.columns:
        metrics_data.sort_values(by='time_stamp')
        metrics_data['iteration'] = np.arange(0,len(metrics_data),1)

    return metrics_data


def ecdf(data):
    """
    Compute Empirical Cumulative Distribution Function
    :param data: Distribution values
    :return: Returns (x, y) in order to plot a distribution function, where x is sorted data, and y is probability.
    """
    x = np.sort(data)
    n = x.size
    y = np.arange(1, n + 1) / n
    return x, y


def calculate_confidence_interval(filepath, iteration_of_convergence=None, generate_plots=True):
    """
    Calculates the contrast, c, where with 90% confidence, actual measured contrast will be below (better) than c.
    Using analytical assumption that mean contrast, µ + 1.28(sigma) is 90% confidence level.
    Displays and saves four plots, with varying analysis, including statistical confidence interval plots.
    :param filepath: str path to The csv or df of data including iteration number and mean contrast
    :param iteration_of_convergence: Default=None, calculated in calculate_iteration_of_convergence
    :param generate_plots: Default=True, plots and saves pdf if true.
    :return: contrast value, c, that the actual measured contrast will be below (better) than c 90% of the time.
    """

    metrics_data = load_metrics_data(filepath)

    if iteration_of_convergence is None:
        iteration_of_convergence, warning_flag = calculate_iteration_of_convergence(filepath)
    elif isinstance(iteration_of_convergence, int):
        log.info(f"Implementing user-specified convergence point at iteration {iteration_of_convergence}")

    converged_metrics = metrics_data[metrics_data['iteration'] >= iteration_of_convergence]
    mean = np.mean(converged_metrics['mean_image_contrast'])
    std = np.std(converged_metrics['mean_image_contrast'])
    n_samples = len(converged_metrics)
    confidence_interval = mean + 1.28 * std
    line_of_90 = int(.9 * n_samples - 1)
    sorted_contrast = converged_metrics['mean_image_contrast'].tolist()
    sorted_contrast.sort()
    empirical_confidence_interval = sorted_contrast[line_of_90]

    if generate_plots:
        fig, (ax1, ax2, ax3, ax4) = plt.subplots(1, 4, figsize=(20, 4))
        fig.suptitle(os.path.split(os.path.dirname(filepath))[-1])
        if warning_flag:
            fig.suptitle("WARNING: CONVERGENCE CRITERIA QUESTIONABLE    " + os.path.split(os.path.dirname(filepath))[-1]
                         + "    WARNING: CONVERGENCE CRITERIA QUESTIONABLE", c='r')
        ax1.axvline(iteration_of_convergence, label='Point of Convergence', c='g')

        ax1.set_yscale('log')
        ax1.plot(metrics_data['iteration'], metrics_data['mean_image_contrast'],c='b', marker='o', alpha = 0.6)
        ax1.plot(converged_metrics['iteration'], converged_metrics['mean_image_contrast'], c='g', marker='o',
                 alpha=0.6)
        ax1.axhline(mean, label=f'Mean: {mean:.3}', c='k', linestyle='-')
        ax1.set_xlabel('Iteration')
        ax1.set_ylabel('Contrast')
        ax1.set_title('Contrast by Iteration')

        ax1.grid(True, which='both', alpha=0.3)
        ax1.legend()

        plt.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))
        ax2.plot(converged_metrics['iteration'], converged_metrics['mean_image_contrast'], c='g', marker='o',
                 alpha=0.6)
        ax2.axhline(confidence_interval, label=f'90% CI: {confidence_interval:.3}', c='k', alpha=0.7, linestyle='-.',
                    linewidth=1.0)
        ax2.axhline(empirical_confidence_interval, label=f'90% Emp: {empirical_confidence_interval:.3}', c='orange',
                    alpha=0.7, linestyle=(0, (5, 1)), linewidth=1.0)
        ax2.axhline(mean, label=f'Mean: {mean:.3}', c='k', linestyle='-')
        ax2.set_xlabel('Iteration')
        ax2.set_ylabel('Contrast')
        ax2.set_title('Convergent Contrast')
        ax2.grid(True, which='both', alpha=0.3)
        ax2.legend()

        ax3.hist(converged_metrics['mean_image_contrast'], ec='black', zorder=3)
        ax3.axvline(confidence_interval, label=f'90% CI: {confidence_interval:.3}', c='k', alpha=0.7, linestyle='-.',
                    linewidth=1.2, zorder=4)
        ax3.axvline(empirical_confidence_interval, label=f'90% Emp: {empirical_confidence_interval:.3}', c='orange',
                    alpha=0.7, linestyle=(0, (5, 1)), linewidth=1.0, zorder=5)
        ax3.axvline(mean, label=f'Mean: {mean:.3}', c='k', linestyle='-', zorder=4)
        ax3.grid(True, which='both', alpha=0.3, zorder=0)
        ax3.set_xlabel('Contrast')
        ax3.set_ylabel('Counts')
        ax3.set_title(f'Distribution of Contrast: {n_samples} iterations')
        plt.ticklabel_format(axis="x", style="sci", scilimits=(0, 0))
        ax3.legend()

        ecdf_x, ecdf_y = ecdf(converged_metrics['mean_image_contrast'])
        ax4.plot(ecdf_x,ecdf_y,alpha=0.8)
        ax4.axvline(confidence_interval, label=f'90% CI: {confidence_interval:.3}', c='k', alpha=0.7, linestyle='-.',
                    linewidth=1.0)
        ax4.axvline(empirical_confidence_interval, label=f'90% Emp: {empirical_confidence_interval:.3}', c='orange',
                    alpha=0.7, linestyle=(0, (5, 1)), linewidth=1.0)
        ax4.axvline(mean, label=f'Mean: {mean:.3}', c='k', linestyle='-')
        ax4.grid(True, which='both', alpha=0.3)
        ax4.set_xlabel('Contrast')
        ax4.set_ylabel('Likelihood of occurance')
        ax4.set_title('Cumulative Distribution: Contrast')
        plt.ticklabel_format(axis="x", style="sci", scilimits=(0, 0))
        ax4.legend()

        output_fn = os.path.join(os.path.split(filepath)[-2],'contrast_metrics.pdf')
        careful_savefig(fig, output_fn)
    return confidence_interval

def plot_environment_and_contrast(filepath):
    """ Plot lab environmental metrology and contrast.
    Intended to help track impacts of lab environment on dark zone experiments.

    """

    metrics_data = load_metrics_data(filepath)
    datetimes = np.asarray(metrics_data['time_stamp'], np.datetime64)

    fig, axes = plt.subplots(nrows=3, ncols=1, figsize=(8, 8), gridspec_kw={'hspace': 0.3, 'top': 0.9})
    fig.suptitle("Lab Environment Metrology during:\n" + os.path.split(os.path.dirname(filepath))[-1], fontweight='bold')

    axes[0].plot(datetimes, metrics_data['temp_(C)'], c='red', marker='+',
                 label='Aux Temperature Sensor')
    axes[0].set_ylabel('Temperature (C)')

    axes[1].plot(datetimes, metrics_data['humidity_(%)'], c='blue', marker='+',
                 label='Aux Humidity Sensor')
    axes[1].set_ylabel('Humidity (%)')

    for i, values in enumerate([metrics_data['temp_(C)'], metrics_data['humidity_(%)']]):
        axes[i].text(0.05, 0.15, f"Mean: {np.mean(values):.2f}       Range: {np.min(values):.2f} - {np.max(values):.2f}       Std dev: {np.std(values):.2f}",
                     color = 'darkred' if i==0 else 'darkblue', transform=axes[i].transAxes)

    axes[2].semilogy(datetimes, metrics_data['mean_image_contrast'], c='purple', marker='o',
                     label='Broadband contrast')
    axes[2].set_ylabel('Contrast')

    # Try to also parse the safety check temp and humidity from the log file
    experiment_log = glob.glob(os.path.join(os.path.dirname(filepath), "*.log"))[0]
    logtable = hicat.plotting.log_analysis_plots.load_log_table(experiment_log)

    for i, qty in enumerate(['Temperature', 'Humidity']):
        safety_check_results = hicat.plotting.log_analysis_plots.query_log_table(logtable, f'{qty} test passed')
        safety_check_times = safety_check_results['datetime']
        safety_check_values = [float(msg.split()[3]) for msg in safety_check_results['message']]
        axes[i].plot(safety_check_times, safety_check_values, c='orange' if i==0 else 'skyblue',
                 marker='|', label=f"Safety {qty} Sensor")
        axes[i].text(0.05, 0.05, f"Mean: {np.mean(safety_check_values):.2f}       Range: "
                                 f"{np.min(safety_check_values):.2f} - {np.max(safety_check_values):.2f}       "
                                 f"Std dev: {np.std(safety_check_values):.2f}",
                     color = 'peru' if i==0 else 'dodgerblue', transform=axes[i].transAxes)
    for ax in axes:
        ax.grid(True, which='both', alpha=0.3)
        ax.legend(loc='upper right')

        locator = matplotlib.dates.AutoDateLocator(minticks=3, maxticks=7)
        formatter = matplotlib.dates.ConciseDateFormatter(locator)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(formatter)

    # ensure all plots have consistent X axes
    for i in [1,2]:
        axes[i].set_xlim(*axes[0].get_xlim())
    # allow Y axis to autoscale but enforce minimum y range +- 1 deg temp or +- 1% humidity
    # This minimum range is semi-arbitrary but helps avoid the text labels landing on top of the
    # plot lines.
    for i in [0,1]:
        ylim = axes[i].get_ylim()
        yrange = ylim[1]-ylim[0]
        if yrange < 2:
            axes[i].set_ylim(min(np.mean(ylim)-1, ylim[0]), max(np.mean(ylim)+1, ylim[1]))

    output_fn = os.path.join(os.path.dirname(filepath), 'environment.pdf')
    careful_savefig(fig, output_fn)

