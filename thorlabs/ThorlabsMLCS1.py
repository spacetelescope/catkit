from __future__ import (absolute_import, division,
                        print_function, unicode_literals)
from builtins import *

from ctypes import *

import os
path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib","uart_library_win64.dll")
print(path)
uart_dll = cdll.LoadLibrary(bytes(path,"utf-8"))


# LISTS ALL COM DEVICES.
# buffer = b"0"*255
# list_code = uart_dll.fnUART_LIBRARY_list(buffer, 255)
# print(buffer)

#if uart_dll.fnUART_LIBRARY_isOpen(b"COM3") != 0:
handle = uart_dll.fnUART_LIBRARY_open(b"COM3", 115200, 3)

# if uart_dll.fnUART_LIBRARY_isOpen(b"COM3") != 1:
#     uart_dll.fnUART_LIBRARY_close(handle)
#     handle = uart_dll.fnUART_LIBRARY_open(b"COM3")


#ACTIVE CHANNEL.
# if handle >= 0:
#     print("Setting channel to 2")
#     #SetActiveChannel 2
#     buf32 = b"0"*32
#     command = "channel=2\r"
#     pad_size = 32 - len(command)
#     padding = "0" * pad_size
#     command = command + padding
#     uart_dll.fnUART_LIBRARY_Set(handle, command, 32)
# else:
#     print("failed to connect")

if handle >= 0:

    # Set Active Channel.
    print("Activate channel 2")
    active_command_string = b"channel=2\r"
    uart_dll.fnUART_LIBRARY_Set(handle, active_command_string, 32)

    print("Enable channel")
    enable_command_string = b"enable=1\r"
    uart_dll.fnUART_LIBRARY_Set(handle, enable_command_string, 32)

    print("Setting Current")
    current_command_string = b"current=80.0\r"
    uart_dll.fnUART_LIBRARY_Set(handle, current_command_string, 32)

else:
    print("failed to connect")





if uart_dll.fnUART_LIBRARY_isOpen(b"COM3") != 1:
    uart_dll.fnUART_LIBRARY_close(handle)

# print("Closed")
# print(uart_dll.fnUART_LIBRARY_isOpen(buffer))
