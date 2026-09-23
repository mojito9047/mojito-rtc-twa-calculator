"""Minimal wrapper around Expedition's ExpDLL.dll.

Reads live instrument channels from a running Expedition on this PC. The DLL
location comes from the registry key Expedition writes on install.
"""

import ctypes
import os
from ctypes import c_int16, c_uint16, c_double, c_bool, c_char_p, POINTER
from enum import IntEnum

EXPEDITION_DLL_REG_KEY = r"SOFTWARE\Expedition\Core"

class Var(IntEnum):
    # Values from TTCMarine/Expedition-Python Expedition/enums.py.
    # Only the channels used by this app are included here.
    # Lat..Sog checked against a running Expedition (v61): the enums.py values
    # 47-50 are one low; 47 is not a position channel. tests/test_api.py pins them.
    Utc = 0
    Bsp = 1
    Awa = 2
    Aws = 3
    Twa = 4
    Tws = 5
    Twd = 6
    Hdg = 13
    Lat = 48
    Lon = 49
    Cog = 50
    Sog = 51

def get_expedition_location():
    import winreg

    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, EXPEDITION_DLL_REG_KEY)
    value, _ = winreg.QueryValueEx(key, "Location")
    return value

class ExpeditionDLL:
    @staticmethod
    def from_default_location():
        return ExpeditionDLL(get_expedition_location())

    def __init__(self, exp_install_dir):
        self.exp_install_dir = exp_install_dir
        dll_path = os.path.join(exp_install_dir, "ExpDLL.dll")
        if not os.path.exists(dll_path):
            raise FileNotFoundError(f"Could not find ExpDLL.dll in {exp_install_dir}")

        self.exp_dll = ctypes.windll.LoadLibrary(dll_path)
        self.exp_dll.GetExpVar.argtypes = [c_int16, POINTER(c_double), c_uint16, POINTER(c_int16)]
        self.exp_dll.GetExpVar.restype = c_bool
    def get_var(self, var, boat=0):
        """Return (value, age) for an Expedition channel; value is None when invalid.

        The age reported by this DLL call has always equalled the channel
        number in testing, so the app does not rely on it.
        """
        value = c_double()
        age = c_int16()

        valid = self.exp_dll.GetExpVar(
            c_int16(var),
            ctypes.byref(value),
            c_uint16(boat),
            ctypes.byref(age)
        )

        if valid:
            return value.value, age.value
        return None, age.value
