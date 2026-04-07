# -*- coding: utf-8 -*-
"""
Generator.py
@author: Groß, Hendrik
"""
import numpy as np
from collections import deque
import dearpygui.dearpygui as dpg
from .IModbusElement import IModbusElement
from .Value import ModbusValue, PandaPowerValue
from .Enum import ReadMode

class Generator(IModbusElement):
    """
    Static generator - represented in ePHASORSIM as ``Positive Sequence Load`` with inverted sign for the power.
    
    This class manages static generators in the network model that can be controlled/read via Modbus or pandapower:
        - **Mandatory internal values**: \n
            - ``p_mw``: Active power in MW (positive = feed-in) \n
            - ``q_mvar``: Reactive power in MVar (positive = capacitive)\n
        - **Possible internal values**: \n
            - ``set_p_mw``: Controlled active power in MW (positive = feed-in) \n
            - ``set_q_mvar``: Controlled reactive power in MVar (positive = feed-in) \n
            - ``profile_p_mw``: Model-controlled active power or theoretical plant active power from the feed-in profile (positive = feed-in) \n
            - ``profile_q_mvar``: Model-controlled reactive power or theoretical plant reactive power from the feed-in profile (positive = feed-in) \n
            - Other internal values are possible, but are then only processed via the standard read/write functionality
        - **PandaPower mapping**: ``sgen`` DataFrame with ``p_mw`` and ``q_mvar`` columns
        - **Additional information**: 
            - P and Q are multiplied by -1 if they come from ePHASORSIM (generation instead of consumption). 
            - If a P value is read, the corresponding Q value must also be read (otherwise errors occur)
    """
    # --------------------------------------------------------------------------------------------------------
    # Class variables
    df_pp = "sgen"
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
    # Kommunikationsmethoden
    async def read_async(self, mode: ReadMode = ReadMode.ALL) -> dict[str, ModbusValue | PandaPowerValue]:
        """
        Reads generator values and updates the internal power state.

        Modbus values are sign-corrected because ePHASORSIM delivers the generator in the consumer reference system. Afterwards, ``s_complex`` is built from P and Q and the visualization is optionally updated.

        :param mode: Data source for the read access (Modbus, pandapower, or both)
        :type mode: ReadMode
        :return: Updated ``values`` dictionary
        :rtype: dict[str, ModbusValue | PandaPowerValue]
        """
        # Read Modbus and/or PandaPower values
        self.values = await super().read_async(mode)
        
        # If data is read from ePHASORSIM, the generator is in the consumer reference system
        # In PandaPower and in general, the values inside this class are shown in the generator reference system
        if isinstance(self.values["p_mw"], ModbusValue):
            self.values["p_mw"].value = -self.values["p_mw"].value
        if isinstance(self.values["q_mvar"], ModbusValue):
            self.values["q_mvar"].value = -self.values["q_mvar"].value

        # Store the power values in object attributes
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
    # Zusatzmethoden: Generator
    def start_visualize(self, _parent: int|str):
        """Extends the standard visualization with a second curve for profile values."""
        super().start_visualize(_parent)

        # If there are theoretical power values, add an additional line series for the theoretical plant power
        if "profile_p_mw" in self.values:
            dpg.configure_item(self.uuid_data, tag=f"S [kVA] (actual)") # pyright: ignore[reportArgumentType]

            # Additional line series
            self.data_value2 = deque(maxlen=self.MAX_DATAPOINTS)
            self.uuid_data2 = dpg.generate_uuid()
            dpg.add_line_series([], [], label=f"S [kVA] (theoretical)", tag=self.uuid_data2, parent=self.uuid_y)  # pyright: ignore[reportArgumentType]

    def update_visualize(self):
        """Updates the visualization including theoretical profile power."""
        super().update_visualize()

        # If there are theoretical power values, update the additional line series
        if "profile_p_mw" in self.values:
            # Calculate the theoretical apparent power, add it to the visualization, and respect the sign if these theoretical values come from ePHASORSIM
            if isinstance(self.values["profile_p_mw"], ModbusValue):
                self.values["profile_p_mw"].value = -self.values["profile_p_mw"].value
                self.values["profile_q_mvar"].value = -self.values["profile_q_mvar"].value
            theo_s_complex = complex(self.values["profile_p_mw"].value,self.values["profile_q_mvar"].value)

            # Add the value to the visualization
            self.data_value2.appendleft(theo_s_complex)
            x_visible, y_visible = self.__filter_line_series_data(self.data_value2)
            dpg.set_value(self.uuid_data2, [x_visible, y_visible])

    # --------------------------------------------------------------------------------------------------------
    # Interne Methoden
    def __repr__(self):
        """
        Creates a compact text representation of the generator for debug output.

        :return: Formatted status string
        :rtype: str
        """
        if np.isnan(self.s_complex.real) or np.isnan(self.s_complex.imag):
            return f"Generator [{self.name}] - Internal 'Values' = {len(self.values)}"
        else:
            return f"Generator [{self.name}] : {abs(self.s_complex):.2f} MVA ({self.s_complex:.3f})"