from __future__ import (absolute_import, division,
                        print_function, unicode_literals)
from builtins import *

from ctypes import *
import os
path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib","uart_library_win64.dll")
print(path)
uart_dll = cdll.LoadLibrary(bytes(path,"utf-8"))
buffer = "0"*255
list_code = uart_dll.fnUART_LIBRARY_list(buffer, 255)

print(list_code)
print(buffer)

print(uart_dll.fnUART_LIBRARY_isOpen(buffer))

handle = uart_dll.fnUART_LIBRARY_open(buffer)
print("Opened")


print(uart_dll.fnUART_LIBRARY_isOpen(buffer))

uart_dll.fnMCLS1_DLL_Close(handle)

print("Closed")
print(uart_dll.fnUART_LIBRARY_isOpen(buffer))
