# -*- coding: utf-8 -*-
"""
Load.py
@author: Groß, Hendrik
"""
import numpy as np
from .IModbusElement import IModbusElement
from .Value import ModbusValue, PandaPowerValue
from .Enum import ReadMode

class Load(IModbusElement):
    """
    Load/consumption object - represented as ``Positive Sequence Load`` in ePHASORSIM.
    
    This class manages loads in the network model that can be controlled/read via Modbus or pandapower:
        - **Mandatory internal values** \n 
            - ``p_mw``: Active power in MW (positive = consumption) \n
            - ``q_mvar``: Reactive power in MVar (positive = inductive)\n
        - **Possible internal values**: \n
            - ``set_p_mw``: Controlled active power in MW \n
            - ``set_q_mvar``: Controlled reactive power in MVar \n
            - Other internal values are possible, but are then only processed via the standard read/write functionality
        - **PandaPower mapping**: ``load`` DataFrame with ``p_mw`` and ``q_mvar`` columns
        - **Additional information**: If a P value is read, the corresponding Q value must also be read (otherwise errors occur)
    """
    # --------------------------------------------------------------------------------------------------------
    # Class variables
    df_pp = "load"
    LIST_VALUE_KEYS: list[str] = ["p_mw","q_mvar"]
    DICT_MEASUREMENT: dict[str,str]= {
        "p_mw": "p",
        "q_mvar": "q"
    }

    # Complex variable representing apparent power with P as the real part and Q as the imaginary part
    s_complex : complex = complex(np.nan, np.nan)

    # Status variables
    p: float = np.nan       # Variable for the simplified representation of the load active power
    q: float = np.nan       # Variable for the simplified representation of the load reactive power
    
    # --------------------------------------------------------------------------------------------------------
    # Komponentenmethoden
    @property
    def value(self) -> float:
        """Returns the magnitude of the complex power in kVA."""
        return abs(self.s_complex)*1000

    @property
    def unit(self) -> str:
        """Returns the unit of the displayed amount of power (``kVA``)."""
        return "kVA"

    # --------------------------------------------------------------------------------------------------------
    # Communication methods
    async def read_async(self, mode: ReadMode = ReadMode.ALL) -> dict[str, ModbusValue | PandaPowerValue]:
        """
        Reads load values from the configured source and updates the state.

        After reading ``p_mw`` and ``q_mvar``, ``s_complex`` is set.
        If a visualization is active, it is updated immediately.

        :param mode: Data source for the read access (Modbus, pandapower, or both)
        :type mode: ReadMode
        :return: Updated ``values`` dictionary
        :rtype: dict[str, ModbusValue | PandaPowerValue]
        """
        # Read Modbus and/or PandaPower values
        self.values = await super().read_async(mode)
        
        # Check whether all dictionary keys are set as expected
        self.p = self.values["p_mw"].value
        self.q = self.values["q_mvar"].value
        
        # Check whether values are available
        if self.p is not None and self.q is not None:
            # Create the complex apparent power value from the values
            self.s_complex = complex(self.p,self.q)

            # If a visualization exists, store the values for visualization and update it
            if self.VIS_INIT:
                # Update the visualization
                self.update_visualize()
        return self.values
    
    # --------------------------------------------------------------------------------------------------------
    # Interne Methoden
    def __repr__(self):
        """
        Creates a compact text representation of the load for debug output.

        :return: Formatted status string
        :rtype: str
        """
        if np.isnan(self.s_complex.real) or np.isnan(self.s_complex.imag):
            return f"Load [{self.name}] -Internal 'Values' = {len(self.values)}"
        else:
            return f"Load [{self.name}] : {abs(self.s_complex):.2f} MVA ({self.s_complex:.3f})"