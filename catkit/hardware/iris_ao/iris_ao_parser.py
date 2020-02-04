import re


def __clean_string(line):
    """
    Convenience function - not sure what it is doing
    """
    return re.sub(r"[\n\t\s]*", "", line)


def __convert_to_float(string):
    """Convert a string to a float, if possible
    """
    return float(string) if string else 0.0


def read_global(path):
    """
    This section of a PTT111 file only has one line and it’s called GV.
    This is a uniform ptt command that goes on all the segments. This dm_function
    reads that line.

    Example: [GV: 0, 0, 0]
    """
    with open(path, "r") as irisao_file:
        # Read global line
        raw_line = irisao_file.readline()

        # Clean up the string.
        clean_first_line = __clean_string(raw_line)

        # Check that the type is "GV"
        if clean_first_line[1:3].upper() == "GV":

            # Remove white space, and split the values.
            global_values = clean_first_line.lstrip("[GV:").rstrip("]").split(",")
            global_float = tuple(map(__convert_to_float, global_values))

            # If all zeros, then move on to the zernikes.
            if not all(v == 0 for v in global_float):
                return global_float
            else:
                return None

        else:
            raise Exception("Iris AO file formatting problem, can't process the global line:\n" + raw_line)


def read_zerkines(path):
    """
    The section of a PTT111 file has one number per global Zernike mode, which are called MV.
    read_zernikes() reads those numbers directly, which is only useful if teh value gets passed
    directly back into the IrisAO hardware control, as we can’t read which individual segment
    has what ptt command

    Example: [MV: 1, 0]
    """
    with open(path, "r") as irisao_file:
        raw_line = irisao_file.readline()
        clean_line = __clean_string(raw_line)

        # Skip to the zernike section:
        while clean_line[1:3].upper() != "MV":
            raw_line = irisao_file.readline()
            clean_line = __clean_string(raw_line)

        zernike_commands = []
        while clean_line[1:3].upper() == "MV":

            # Parse line and create of tuples (zernike, value).
            zernike_string_list = clean_line.lstrip("[MV:").rstrip("]").split(",")
            zernike_type = int(zernike_string_list[0])
            zernike_value = __convert_to_float(zernike_string_list[1])

            if zernike_value != 0:
                zernike_commands.append((zernike_type, zernike_value))

            raw_line = irisao_file.readline()
            clean_line = __clean_string(raw_line)

        if zernike_commands:
            return zernike_commands
        else:
            return None


def read_segments(path):
    """
    Read the zerinke values for P T T for each segment
    In this section of a PTT111 file, each segment gets a ptt command (ZV), which
    is read by this function. In this case, the lines are populated with the segment
    number, piston, tip, tilt.

    Example : [ZV: 1, 0, 0, 0]
    """
    with open(path, "r") as irisao_file:
        raw_line = irisao_file.readline()
        clean_line = __clean_string(raw_line)

        # Skip to the segment section:
        while clean_line[1:3].upper() != "ZV":
            raw_line = irisao_file.readline()
            clean_line = __clean_string(raw_line)

        segment_commands = {}
        while clean_line[1:3].upper() == "ZV":

            # Parse into dictionary {segment: (piston, tip, tilt)}.
            segment_string_list = clean_line.lstrip("[ZV:").rstrip("]").split(",")
            segment_num = int(segment_string_list[0])
            segment_tuple = __convert_to_float(segment_string_list[1]), \
                            __convert_to_float(segment_string_list[2]), \
                            __convert_to_float(segment_string_list[3])

            if any(segment_tuple):
                segment_commands[segment_num] = segment_tuple

            raw_line = irisao_file.readline()
            clean_line = __clean_string(raw_line)

        if segment_commands:
            # Prepare command for segments.
            return segment_commands
        else:
            return None


def read_file(path, num_segments=37):
    """
    Read the entirety of a PTT111 file

    #TODO: do I want to limit the number of segments?
    """

    # Read the global portion of the file, and return the command if it's present.
    global_command = read_global(path)
    if global_command is not None:

        # Create a dictionary and apply global commands to all segments.
        command_dict = {}
        for i in range(num_segments):
            command_dict[i + 1] = global_command
        return command_dict

    # Read in the zernike aka "modal" lines and do error checking.
    zernike_commands = read_zerkines(path)
    if zernike_commands is not None:
        return zernike_commands

    # Read in the segment commands.
    segment_commands = read_segments(path)
    if segment_commands is not None:
        return segment_commands

    # No command found in file.
    return None




#TODO: add below to iris_ao_parser?
def read_ini(path, num_segments=37):
    """
    Read the Iris AO segment PTT parameters from an .ini file into Iris AO style
    dictionary {segnum: (piston, tip, tilt)}.

    This expects 37 segments with centering such that it is in the center of the IrisAO

    :param path: path and filename of ini file to be read
    :return: dict; {segnum: (piston, tip, tilt)}
    """
    config = ConfigParser()
    config.optionxform = str   # keep capital letters
    config.read(path)

    nbSegment = config.getint('Param', 'nbSegment')
    segment_commands = {}

    for i in range(nbSegment):
        section = 'Segment{}'.format(i+1)
        piston = float(config.get(section, 'z'))
        tip = float(config.get(section, 'xrad'))
        tilt = float(config.get(section, 'yrad'))
        segment_commands[i+1] = (piston, tip, tilt)

    return segment_commands

def read_array(array, as_si=True):
    #TODO Update for any number of segments
    """
    Create an Iris AO wavefront map dictionary in microns and rad from an array in meters and radians.

    segments:
    mapping: simcen -> simcen
    :param wf_array:
    :return: dict; Iris AO style wavefront map {seg: (piston, tip, tilt)}


    Take in an array of tuples of piston tip tilt for a set of segments.

    Need to make some assumptions about this array. 
    """
    # Create array of number segments we talk to.
    segnum = array.shape[0]
    if segnum != 19:   # we can currently work only with arrays with exactly 19 entries
        raise Exception('Input array must have shape (19, 3).')


    seglist = np.arange(segnum)

    # Put surface information in dict
    command_dict = {seg: tuple(ptt) for seg, ptt in zip(seglist, wf_array)}

    # Convert from meters and radians to um and mrad.
    if as_si:
        command_dict = convert_dict_from_si(command_dict)

    # Round to 3 decimal points after zero.
    rounded = {seg: (np.round(ptt[0], 3), np.round(ptt[1], 3),
                     np.round(ptt[2], 3)) for seg, ptt in list(wf_dict.items())}

    return rounded


def read_command(command):
    """
    Take in command that can be .PTT111, .ini, array, or dictionary (of length #of segments in pupil)
    Dictionary units must all be the same (microns and millirads?)
    -- TODO - add function for converting units?
    -- TODO - constantly check that the command is the correct length

    :return command_dict: dict, command in the form of a dictionary
    """
    try:
        if command.endswith("PTT111"):
            command_dict = read_segments(command)
            as_si = False
        elif path.endswith("ini"):
            command_dict = read_ini_to_dict(command)
            as_si = False
        else:
            raise Exception("The command input format is not supported")
    except:
        if isinstance(command, dict):'
            command_dict = command
            as_si = True # TODO: UNITS! ? !
        elif isinstance(command, (list, tuple, np.ndarray)):
            # TODO: Currently dict_from_array expects m and radians
            command_dict = read_array(command)
            as_si = False
        else:
            raise Exception("The command input format is not supported")

    # Check that lengths are correct
    if len(command_dict) != self.number_segments_in_pupil:
        raise Exception("The number of segments in your command MUST equal number of segments in the pupil")

    return command_dict, as_si


def convert_dict_from_si(command_dict):
    """
    Take a wf dict and convert from SI (meters and radians) to microns and millirads
    """
    converted = {seg: (ptt[0]*(u.m).to(u.um), ptt[1]*(u.rad).to(u.mrad), ptt[2]*(u.rad).to(u.mrad)) for
                 seg, ptt in list(wf_dict.items())}

    return converted
