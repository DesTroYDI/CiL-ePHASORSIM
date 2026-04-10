# -*- coding: utf-8 -*-
"""
Transformer2W.py
@author: Groß, Hendrik
"""
import numpy as np
from .IModbusElement import IModbusElement
from .Value import ModbusValue, PandaPowerValue
from .Enum import ReadMode

class Transformer2W(IModbusElement):
    """
    Transformer2W - two-winding transformer of the network model to which all other elements are connected.

    **IMPORTANT: If the tap changer is writable in ePHASORSIM, the initial value in the HOLDING register must match the starting value from pandapower**

    This class manages two-winding transformers in the network model that can be controlled/read via Modbus or pandapower.
    The tap changer (``tap_pos``) is internally converted into the ePHASORSIM-compatible off-nominal ratio (pu).

        - **Required internal values**:
            - ``loading_percent``: Transformer loading in % ('ro' from pandapower)
            - ``tap_pos``: Current tap changer position (rw, to/from pandapower)
        - **Possible internal values**:
            - ``set_rW1``: Off-nominal ratio for winding 1 to be written/stored (for ePHASORSIM)
            - ``set_rW2``: Off-nominal ratio for winding 2 to be written/stored (for ePHASORSIM)
            - Other internal values are possible, but then they are only processed via the standard read/write functionality

        - **PandaPower mapping**: ``trafo`` DataFrame with ``loading_percent``, ``tap_pos``, ``tap_step_percent``, ``tap_neutral``, ``tap_min``, ``tap_max``, ``tap_side``
    """
    # --------------------------------------------------------------------------------------------------------
    # Class variables
    df_pp = "trafo"
    LIST_VALUE_KEYS: list[str] = ["loading_percent","tap_pos"]

    # Internal static parameters (initialized once per instance)
    tap_step_percent: float
    tap_neutral: float
    tap_side: str

    # Internal state variables
    loading_percent: float = np.nan
    tap_pos: int = 0
    ratio_w1: float = np.nan   # calculated off-nominal ratio for ePHASORSIM
    ratio_w2: float = np.nan   # calculated off-nominal ratio for ePHASORSIM
    # --------------------------------------------------------------------------------------------------------
    # Component methods
    @property
    def value(self) -> float:
        """Returns the current transformer loading in percent."""
        return self.loading_percent

    @property
    def unit(self) -> str:
        """Returns the unit of the loading value (``%``)."""
        return "%"
    
    # --------------------------------------------------------------------------------------------------------
    # Helper methods: tap_pos <-> ratio_w1/ratio_w2
    def __get_trafo_params(self):
        """Reads static transformer parameters and validates optional ratio keys."""
        # If "rW1"/"set_rW1" exists, then "rW2"/"set_rW2" must also exist.
        if "set_rW1" in self.values and not "set_rW2" in self.values:
            raise ValueError(f"TRF_VALUE_ERROR - Value error in transformer '{self.name}'. 'set_rW1' exists without 'set_rW2'")
        if "rW1" in self.values and not "rW2" in self.values:
            raise ValueError(f"TRF_VALUE_ERROR - Value error in transformer '{self.name}'. 'rW1' exists without 'rW2'")
        
        # Read the static variables
        self.tap_step_percent = self.pp_net.trafo.at[self.net_index, "tap_step_percent"]
        self.tap_neutral      = self.pp_net.trafo.at[self.net_index, "tap_neutral"]
        self.tap_side         = str(self.pp_net.trafo.at[self.net_index, "tap_side"]).lower()

    def tap_pos_to_ratios(self, tap_pos: int) -> tuple[float, float]:
        """
        Converts ``tap_pos`` into ePHASORSIM off-nominal ratios.

        - ``tap_side='hv'``: ``ratio_w1 = f(tap_pos)``, ``ratio_w2 = 1``
        - ``tap_side='lv'``: ``ratio_w1 = 1``, ``ratio_w2 = f(tap_pos)``

        :param tap_pos: Tap changer position from pandapower
        :type tap_pos: int
        :return: Tuple (ratio_w1, ratio_w2)
        :rtype: tuple[float, float]
        """
        if not hasattr(self, "tap_side"):
            self.__get_trafo_params()

        # ratio = 1 + (tap_pos - tap_neutral) * tap_step_percent / 100
        delta = (tap_pos - self.tap_neutral) * self.tap_step_percent / 100.0
        ratio = 1.0 + delta

        # Adjust the ratio depending on ``tap_side``
        if self.tap_side == "lv":
            return 1.0, ratio
        return ratio, 1.0

    def ratio_to_tap_pos(self, ratio: float) -> int:
        """
        Converts an off-nominal ratio back into ``tap_pos``.

        :param ratio: Off-nominal ratio from ePHASORSIM (pu)
        :type ratio: float
        :return: Rounded tap changer position for pandapower
        :rtype: int
        """
        # Check whether static transformer variables are still needed
        if not hasattr(self, "tap_step_percent"):
            self.__get_trafo_params()

        if self.tap_step_percent == 0:
            return int(self.tap_neutral)
        return int(round((ratio - 1.0) / (self.tap_step_percent / 100.0) + self.tap_neutral))

    # --------------------------------------------------------------------------------------------------------
    # Communication methods
    async def read_async(self, mode: ReadMode = ReadMode.ALL) -> dict[str, ModbusValue | PandaPowerValue]:
        """
        Reads transformer values and updates internal state variables.

        After reading, ``loading_percent`` and ``tap_pos`` are set. If
        ``set_rW1``/``set_rW2`` are present, the associated ratios are computed from
        ``tap_pos`` and written into the optional values.

        :param mode: Data source for the read access (Modbus, pandapower, or both)
        :type mode: ReadMode
        :return: Updated ``values`` dictionary
        :rtype: dict[str, ModbusValue | PandaPowerValue]
        """
        # Read Modbus and/or PandaPower values
        self.values = await super().read_async(mode)

        # Transfer the mandatory values into internal state variables
        self.loading_percent = self.values["loading_percent"].value
        self.tap_pos         = int(self.values["tap_pos"].value)

        # Calculate tap_pos -> ratio_w1/ratio_w2 for ePHASORSIM
        # If optional values are present, overwrite them
        if self.tap_pos is not None and "set_rW1" in self.values:
            # Convert to the respective winding depending on the tap side
            self.ratio_w1, self.ratio_w2 = self.tap_pos_to_ratios(int(self.tap_pos))
            self.values["set_rW1"].value = self.ratio_w1
            self.values["set_rW2"].value = self.ratio_w2

        # If a visualization exists, store the values for visualization and update it
        if self.VIS_INIT:
            self.update_visualize()

        return self.values

    # --------------------------------------------------------------------------------------------------------
    # Internal methods
    def __repr__(self):
        """Creates a compact text representation of the transformer.

        :return: Formatted status string
        :rtype: str
        """
        _value = self.loading_percent
        if np.isnan(_value):
            return f"Transformer2W [{self.name}] - Number of internal 'Values' = {len(self.values)}"
        else:
            return f"Transformer2W '{self.name}': Loading= {_value:.2f} {self.unit} with tap position '{self.tap_pos}'"
