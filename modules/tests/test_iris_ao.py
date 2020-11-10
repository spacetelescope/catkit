import hicat.hardware.testbed_state as testbed_state
import hicat.experiments.modules.iris_ao as iris_ao


def test_iris_ao_commands():
    """ Create some basic iris commands and send them to the (simulated) hardware.
    """
    for cmd_func in (iris_ao.letter_f, iris_ao.flat_command):
        command_obj = cmd_func()
        if testbed_state.simulation:
            iris_ao.place_command_on_iris_ao(command_obj, seconds_to_hold_shape=0, verbose=False)

