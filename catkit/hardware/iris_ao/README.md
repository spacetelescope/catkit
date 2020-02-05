# Iris AO

If you have an Iris AO segmented DM, congratulations! You are one of only a few.

The `catkit` module for the Iris AO expects that you will be passing in one of the following types:

* .PTT111 file: File format of the command coming out of the IrisAO GUI
* .ini file: File format of command that gets sent to the IrisAO controls
* array: Format that POPPY outputs if generating command in POPPY

Each of these types has to be handled slightly differently, but never fear, we figured that out for you!

We have also included here some util functions that might come in handy and a module for creating your own custom command with POPPY.

Note that if you have an Iris AO segmented DM, you will need to add an "iris_ao" section to your config.ini file:

* mirror_serial: The mirror serial number. This corresponds to a .mcf file that *MUST* include the driver serial number under "Smart Driver"
* driver_serial: The dirver serial number. This corresponds to a .dcf file.
* nb_segments: The number of segments in your Iris AO DM (including any non-funtioning segments). Always 37. TODO: DO WE WANT THIS?
* pupil_nb_seg: The number of segments in your specific pupil (for most folx, this is less than 37). TODO: DO WE WANT THIS?
* segments_used: A list of the segment numbers that are used in your pupil. The first segment is the center segment, then the following segments are in order from "up" to the next ring, and then counter clockwise. Note that "up" for the Iris hardware is in the direction of segment number 20. For example, if your pupil is centered on segment 3 and is only one ring, then segments_used = [3, 9, 10, 11, 4, 1, 2]

* flatfile_ini: The location of the custom flat .ini file for your Iris AO DM.  
* c_code_ptt_file: The location of the ConfigPTT.ini file which is the file that contains whatever command you want to put on the DM.
* path_to_dm_exe: The path to the directory that houses the DM_Control.exe file
* full_path_dm_exe: The path to (and including) the DM_Control.exe file

Optional (if using POPPY, you will need these - they should be the same for all IrisAO DMs):
* flat_to_flat: The flat side to flat side diameter of each segment in units of mm
* gap_um: The size of the gap between segments in units of um


Example:
[iris_ao]
mirror_serial = 'PWA##-##-##-####'
driver_serial = '########'
nb_segments = 37
pupil_nb_seg = 19
segments_used = [3, 9, 10, 11, 4, 1, 2, 21, 22, 23, 24, 25, 12, 13, 5, 6, 7, 19, 8]
flat_to_flat = 1.4
gap_um = 10
flatfile_ini = ${optics_lab:local_repo_path}/DM/MirrorControlFiles/CustomFLAT.ini
c_code_ptt_file = ${optics_lab:local_repo_path}/DM/MirrorControlFiles/ConfigPTT.ini
path_to_dm_exe = ${optics_lab:local_repo_path}Control DM/Code/release
full_path_dm_exe = ${optics_lab:local_repo_path}Control DM/Code/release/DM_Control.exe
