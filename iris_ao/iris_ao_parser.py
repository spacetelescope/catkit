import re


def __clean_string(line):
    return re.sub(r"[\n\t\s]*", "", line)


def __convert_to_float(string):
    return float(string) if string else 0.0


def read_global(path):
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
