import numpy as np
from scipy import signal 



def fake_centroid(array):
     sum_x = np.sum(array, axis=0)
     sum_y = np.sum(array, axis=1)
     x_peaks = signal.find_peaks_cwt(sum_x, np.arange(5,20))
     y_peaks = signal.find_peaks_cwt(sum_y, np.arange(5,20))
     
     x_tups = [(x_peak, sum_x[x_peak]) for x_peak in x_peaks]
     y_tups = [(y_peak, sum_y[y_peak]) for y_peak in y_peaks]
     x_tups.sort(key=lambda x: x[1], reverse=True)
     y_tups.sort(key=lambda y: y[1], reverse=True)
     
     centroid = []
     for axis in [x_tups, y_tups]:
         if axis[0][1] - axis[1][1] > 1000:
             #print('Just one peak @ {}'.format(axis[0][1]))
             centroid.append(axis[0][0])
         else:
             #print('Two peaks @ {} and {}'.format(axis[0][1], axis[1][1]))
             centroid.append((axis[0][0] + axis[1][0])*.5)
     
     return centroid

