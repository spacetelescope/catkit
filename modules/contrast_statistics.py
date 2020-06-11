import matplotlib.pyplot as plt
import numpy as np
import pandas
import os


def calculate_iteration_of_convergence(metrics_data, slope_threshold=0.0008):
    """
    Calculate the iteration at which the contrast converges. Uses a slope estimate first. If this fails to converge,
    it simply returns n/2 (iteration at the halfway point) and throws a warning.
    :param metrics_data: The csv or df of data including iteration number and mean contrast (may inc. humidity & temp)
    :param slope_threshold: Threshold that slope must be below to be considered 'converged'
    :return: number of the iteration at which the slope *first* crosses the slope_threshold.
    """
    if type(metrics_data) == str:
        metrics_data = pandas.read_csv(metrics_data)

    contrast_fit = np.polyfit(metrics_data['iteration'], np.log(metrics_data[' mean image contrast']), 5)
    fit_1d = np.poly1d(contrast_fit)
    derivative_1d = np.polyder(fit_1d)
    metrics_data['derivatives'] = derivative_1d(metrics_data['iteration'])
    convergence_metrics = metrics_data[np.abs(metrics_data['derivatives']) < slope_threshold]

    # Warning fix this: selects last half of data if no convergence
    if len(convergence_metrics) == 0:
        print("Warning: Iterations do not converge to required slope threshold. Selecting last half of data.")
        iteration_of_convergence = int(metrics_data['iteration'].iloc[-1] / 2)
    elif len(convergence_metrics) >= 1:
        iteration_of_convergence = convergence_metrics['iteration'].iloc[0]
        print(f"Slope threshold reached at iteration {iteration_of_convergence}")

    return iteration_of_convergence


def ecdf(data):
    """ Compute ECDF """
    x = np.sort(data)
    n = x.size
    y = np.arange(1, n + 1) / n
    return x, y


def calculate_confidence_interval(metrics_data, filepath='', iteration_of_convergence=None, generate_plots=True):
    """
    Calculates the conrtrast, c, where with 90% confidence, actual measured contrast will be below (better) than c.
    Using analytical assumption that mean contrast, µ + 1.28(sigma) is 90% confidence level.
    :type filepath: str
    :param metrics_data: The csv or df of data including iteration number and mean contrast (may inc. humidity & temp)
    :param iteration_of_convergence: Default=None, calculated in calculate_iteration_of_convergence
    :return: contrast value, c, that the actual measured contrast will be below (better) than c 90% of the time.
    """
    if type(metrics_data) == str:
        metrics_data = pandas.read_csv(metrics_data)

    if iteration_of_convergence == None:
        iteration_of_convergence = calculate_iteration_of_convergence(metrics_data)
    elif type(iteration_of_convergence) == int:
        print(f"Implementing user-specified convergence point at iteration {iteration_of_convergence}")

    converged_metrics = metrics_data[metrics_data['iteration'] >= iteration_of_convergence]
    mean = np.mean(converged_metrics[' mean image contrast'])
    std = np.std(converged_metrics[' mean image contrast'])
    n_samples = len(converged_metrics)
    confidence_interval = mean + 1.28 * std

    if generate_plots:
        fig, (ax1, ax2, ax3, ax4) = plt.subplots(1, 4, figsize=(20, 4))
        fig.suptitle(os.path.split(filepath)[-1])
        ax1.axvline(iteration_of_convergence, label='Point of Convergence', c='g')
        ax1.set_yscale('log')
        ax1.plot(metrics_data['iteration'], metrics_data[' mean image contrast'],c='b', marker='o', alpha = 0.6)
        ax1.plot(converged_metrics['iteration'], converged_metrics[' mean image contrast'], c='g', marker='o',
                 alpha=0.6)
        ax1.axhline(mean, label=f'Mean: {mean:.3}', c='k', linestyle='-')
        ax1.axhline(confidence_interval, label=f'90% CI: {confidence_interval:.3}', c='k', alpha=0.7, linestyle='-.')
        ax1.set_xlabel('Iteration')
        ax1.set_ylabel('Contrast')
        ax1.set_title('Contrast by Iteration')
        ax1.grid(True, which='both')
        ax1.legend()

        ax2.set_yscale('log')
        ax2.plot(converged_metrics['iteration'], converged_metrics[' mean image contrast'], c='g', marker='o',
                 alpha=0.6)
        ax2.axhline(confidence_interval, label=f'90% CI: {confidence_interval:.3}', c='k', alpha=0.7, linestyle='-.')
        ax2.axhline(mean, label=f'Mean: {mean:.3}', c='k', linestyle='-')
        ax2.set_xlabel('Iteration')
        ax2.set_ylabel('Contrast')
        ax2.set_title('Post-Convergence Contrast')
        ax2.grid(True, which='both')
        ax2.legend()

        ax3.hist(converged_metrics[' mean image contrast'], bins=30, ec='black', alpha=0.8)
        ax3.axvline(confidence_interval, label=f'90% CI: {confidence_interval:.3}', c='k', alpha=0.7, linestyle='-.')
        ax3.axvline(mean, label=f'Mean: {mean:.3}', c='k', linestyle='-')
        ax3.grid(True, which='both')
        ax3.set_xlabel('Contrast')
        ax3.set_ylabel('Counts')
        ax3.set_title(f'Distribution of Contrast: {n_samples} iterations')

        plt.ticklabel_format(axis="x", style="sci", scilimits=(0, 0))
        ax3.legend()


        ecdf_x, ecdf_y = ecdf(converged_metrics[' mean image contrast'])

        ax4.plot(ecdf_x,ecdf_y,alpha=0.8)
        ax4.axvline(confidence_interval, label=f'90% CI: {confidence_interval:.3}', c='k', alpha=0.7, linestyle='-.')
        ax4.axvline(mean, label=f'Mean: {mean:.3}', c='k', linestyle='-')
        ax4.grid(True, which='both')
        ax4.set_xlabel('Contrast')
        ax4.set_ylabel('Liklihood of occurance ')
        ax4.set_title('Cumulative Distribution: Contrast')
        plt.ticklabel_format(axis="x", style="sci", scilimits=(0, 0))
        ax4.legend()

        plt.subplots_adjust(left=None, bottom=None, right=None, top=None, wspace=0.4, hspace=None)
        fig.savefig(f'{filepath}contrast_metrics.pdf', dpi=300, bbox_inches='tight')

    return confidence_interval