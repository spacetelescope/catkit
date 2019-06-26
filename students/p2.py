###IMPORTS
#Camera imports
import ZWOCamera

#Controller imports
import controller_interface

#Picomotor imports
import newport_interface

#Centroid imports
from astropy.io import fits
import matplotlib.pyplot as plt
import numpy as np
from photutils import centroid_1dg
import time



###Constants
sci_cam_x = 960
sci_cam_y = 482
ta_cam_x = 1231.53
ta_cam_y = 496.96

###Creating controller object
ctrl = controller_interface.Controller()
ctrl.command("loop", 1, 0)
ctrl.command("loop", 2, 0)

# ###CALIBRATION
print("Calibrating science camera picomotors...\n")
print("Calibrating X...\n")
zwo_cam_tac = ZWOCamera.ZWOCamera()
zwo_cam_tac.open_camera("ZWO ASI290MM(1)")
zwo_cam = ZWOCamera.ZWOCamera()
zwo_cam.open_camera("ZWO ASI290MM(2)") #Open by name
pm = newport_interface.NewportPicomotor()
#X
pre_image = zwo_cam.take_exposure(exp_time=10)
#zwo_cam.plot_image(pre_image, output_name='test_image_precal.png')
pm.command('relative_move',1,100)
time.sleep(2)
post_image = zwo_cam.take_exposure(exp_time=10)
pm.convert_move_to_pixel(pre_image,post_image, -100, 1)

#Y
print("Calibrating Y...\n")
pre_image = zwo_cam.take_exposure(exp_time=10)
pm.command('relative_move',2,100)
time.sleep(2)
post_image = zwo_cam.take_exposure(exp_time=10)
#zwo_cam.plot_image(post_image, output_name='test_image_postcal.png')
pm.convert_move_to_pixel(pre_image,post_image, -100, 2)
# print(pm.r_ratio_1)
# print(pm.r_ratio_2)
# print(pm.delta_theta_1)
# print(pm.delta_theta_2)



# ##MOVE PICO MOTORS (SCIENCE CAMERA) ONE
print("Aligning beam through hole (move 1 of 2)...\n")
regular = zwo_cam.take_exposure(exp_time=100)
zwo_cam.plot_image(regular, output_name='test_image.png')
# #Move picomotors accoringly...
beam_x, beam_y = centroid_1dg(regular)
pm.command('relative_move',1, -1*(beam_x-sci_cam_x)/pm.r_ratio_1)
time.sleep(2)
pm.command('relative_move',2, -1*(beam_y-sci_cam_y)/pm.r_ratio_2)
time.sleep(2)
regular2 = zwo_cam.take_exposure()
zwo_cam.plot_image(regular2, output_name='test_image_after.png')




# ##MOVE PICO MOTORS (SCIENCE CAMERA) TWO
print("Aligning beam through hole (move 2 of 2)...\n")
regular = zwo_cam.take_exposure()
zwo_cam.plot_image(regular, output_name='test_image2.png')
# #Move picomotors accoringly...
beam_x, beam_y = centroid_1dg(regular)
pm.command('relative_move',1, -1*(beam_x-sci_cam_x)/pm.r_ratio_1)
time.sleep(2)
pm.command('relative_move',2, -1*(beam_y-sci_cam_y)/pm.r_ratio_2)
time.sleep(2)
regular2 = zwo_cam.take_exposure()
zwo_cam.plot_image(regular2, output_name='test_image2_after.png')



###CLOSE THE LOOP
print("Closing loop two...\n")
#input("Press enter to continue.")
#Gain values
time.sleep(2)
p_gain1 = .002
d_gain1 = 0
i_gain1 = 3
p_gain2 = .002
d_gain2 = 0
i_gain2 = 3

#Close loop
ctrl.command("p_gain",1, p_gain1)
ctrl.command("d_gain",1,d_gain1)
ctrl.command("i_gain",1, i_gain1)
ctrl.command("p_gain", 2, p_gain2)
ctrl.command("d_gain", 2, d_gain2)
ctrl.command("i_gain", 2, i_gain2)
time.sleep(.5)
ctrl.command("loop",2,1)
print("Loop two is closed. Closing loop one...\n")
#input("Press enter to continue.")
time.sleep(.5)
ctrl.command("loop",1,1)

ctrl.get_status(1)
ctrl.get_status(2)


print("Both loops closed.\n")
#input("Press enter to continue.")

time.sleep(2)


# ##MOVE PICO MOTORS (TARGET AQUISITION CAMERA) 
# #Move picomotors accoringly...
pm = newport_interface.NewportPicomotor()
#Calibration
print("Calibrating target aquisition picomotors...")
print("Calibrating X...\n")
#X

pre_image = zwo_cam_tac.take_exposure(exp_time=10)
pm.command('relative_move',3,100)
time.sleep(2)
post_image = zwo_cam_tac.take_exposure(exp_time=10)
pm.convert_move_to_pixel(pre_image,post_image, 100, 3)

#Y
print("Calibrating Y...\n")
pre_image = zwo_cam_tac.take_exposure(exp_time=10)
pm.command('relative_move',4,100)
time.sleep(2)
post_image = zwo_cam_tac.take_exposure(exp_time=10)
pm.convert_move_to_pixel(pre_image,post_image, 100, 4)
# print(pm.r_ratio_3)
# print(pm.r_ratio_4)
# print(pm.delta_theta_3)
# print(pm.delta_theta_4)


# # ##TAKE AN EXPOSURE FROM TARGET AQUISITION CAMERA
print("Performing precise centering...")
image = zwo_cam_tac.take_exposure(exp_time=10)
#Save plots
zwo_cam_tac.plot_image(image, output_name='image_TAC.png')
beam_x, beam_y = centroid_1dg(image)

pm.command('relative_move',3, -1*(beam_x-ta_cam_x)/pm.r_ratio_3)
time.sleep(2)
pm.command('relative_move',4, -1*(beam_y-ta_cam_y)/pm.r_ratio_4)
time.sleep(2)


input("System complete. Press enter to exit...\n")
ctrl.command("loop", 1, 0)
ctrl.command("loop", 2, 0)
