# -*- coding: utf-8 -*-
"""
Switch.py
@author: Groß, Hendrik
"""
import numpy as np
from .IModbusElement import IModbusElement

class Switch(IModbusElement):
    """
    Switch - represented as ``Switch`` in ePHASORSIM.

    This class manages switching states in the network model that can be controlled/read via Modbus or PandaPower:
        - **Required internal values** \n
            - ``closed``: Current switching state (whether it is controllable or not, and whether HOLDING or INPUT register is used, depends on the configuration) \n
            - Other internal values are possible, but then they are only processed via the standard read/write functionality
        - **PandaPower mapping**: ``switch`` DataFrame with ``closed``
    """
    # --------------------------------------------------------------------------------------------------------
    # Class variables
    df_pp = "switch"
    LIST_VALUE_KEYS: list[str] = ["closed"]
    
    # --------------------------------------------------------------------------------------------------------
    # Component methods
    @property
    def value(self) -> bool:
        """Returns the switching state as a boolean value."""
        return bool(self.values["closed"].value)

    @property
    def unit(self) -> str:
        """Switching states have no physical unit."""
        return ""
    
    # --------------------------------------------------------------------------------------------------------
    # Internal methods
    def __repr__(self):
        """Creates a compact text representation of the switch.

        :return: Formatted status string
        :rtype: str
        """
        _value = self.values["closed"].value
        if np.isnan(_value):
            return f"Switch [{self.name}] - Number of internal 'Values' = {len(self.values)}"
        else:
            text = "open"
            if _value:
                text = "closed"
            return f"Switch '{self.name}': switch is {text}"