# -*- coding: utf-8 -*-
"""
Enum.py
@author: Groß, Hendrik
"""
from enum import Enum

class ReadMode(Enum):
    """Defines from which source values are read."""
    MODBUS     = "modbus"       
    PANDAPOWER = "pandapower"   
    ALL        = "all"          
    
class ModbusDataType(Enum):
    """
    COIL            -> 1 Bit, Read/Write
    DISCRETE_INPUT  -> 1 Bit, Read Only
    INPUT_REGISTER  -> 16 Bit, Read Only
    HOLDING_REGISTER-> 16 Bit, Read/Write
    """
    COIL = "coil"                           # Range of addresses 0xxxx
    DISCRETE_INPUT = "discrete_input"       # Range of addresses 1xxxx
    INPUT_REGISTER = "input_register"       # Range of addresses 3xxxx
    HOLDING_REGISTER = "holding_register"   # Range of addresses 4xxxx

    @classmethod
    def values(cls):
        """Returns all enum values as a list of strings."""
        return [member.value for member in cls]

    @property
    def is_bit_type(self) -> bool:
        """Checks whether the Modbus type is a 1-bit data type."""
        return self in {self.COIL, self.DISCRETE_INPUT}

    @property
    def is_read_only(self) -> bool:
        """Checks whether the Modbus type is read-only."""
        return self in {self.DISCRETE_INPUT, self.INPUT_REGISTER}

class DataType(Enum):
    """
    Enumeration of the supported data types UINT16, INT16, UINT32, INT32 and FLOAT32.
    (https://opal-rt.atlassian.net/wiki/spaces/PRD/pages/144215818/Modbus+Slave)
    """
    # 16 Bit (1 Register)
    UINT16 = ("uint16", 1)
    INT16 = ("int16", 1)

    # 32 Bit (2 Register)
    UINT32 = ("uint32", 2)
    INT32 = ("int32", 2)
    FLOAT32 = ("float32", 2)

    # Constructor
    def __init__(self, label: str, register_count: int):
        """Stores the label and register count of the data type."""
        self.label = label
        self.register_count = register_count

    @classmethod
    def from_label(cls, label: str) -> "DataType":
        """Searches for a data type by its label."""
        for member in cls:
            if member.label == label:
                return member
        raise ValueError(f"Unknown DataType: {label}")

    @classmethod
    def values(cls):
        """Returns all data type labels as a list."""
        return [member.label for member in cls]