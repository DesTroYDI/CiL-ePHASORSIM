# -*- coding: utf-8 -*-
"""
Bus.py
@author: Groß, Hendrik
"""
import numpy as np
import math
import dearpygui.dearpygui as dpg
from .IModbusElement import IModbusElement
from .Value import ModbusValue, PandaPowerValue
from .Enum import ReadMode

class Bus(IModbusElement):
    """
    Network node (bus) - a connection point in a network model where other elements are attached.
    
    **Functionality:**
        - Read-only (either via Modbus or pandapower)
        - Writing values is not implemented or is only possible through standard functionality (e.g. a short circuit at a bus in ePHASORSIM via `trip`)
        - Mandatory internal **values**:
            - 'vm_pu': Voltage magnitude in p.u.
            - 'va_degree': Voltage angle in degrees
    
    **Voltage calculation:**
        - The complex voltage is derived from magnitude and angle
        - The nominal voltage is obtained from the corresponding PandaPower bus
        - The voltage magnitude can be in 'p.u.' (per unit) or 'V'
    """
    # --------------------------------------------------------------------------------------------------------
    # Class variables
    df_pp = "bus"
    LIST_VALUE_KEYS: list[str] = ["vm_pu","va_degree"]
    DICT_MEASUREMENT: dict[str,str]= {
        "vm_pu": "v",
        "va_degree": "va"
    }

    # Variable that represents the base voltage (in kV) of the bus. It is read from the corresponding PandaPower bus
    base_voltage: float = -1
    # Complex voltage at the bus (either in p.u. or kV, depending on whether base_voltage is set)
    voltage_complex : complex = np.nan 

    # --------------------------------------------------------------------------------------------------------
    # Component methods
    @property
    def value(self) -> float:
        """Returns the magnitude of the currently calculated complex voltage."""
        return abs(self.voltage_complex)

    @property
    def unit(self) -> str:
        """Returns ``kV`` when a base voltage is available, otherwise ``p.u.``."""
        if self.base_voltage > 0:
            return "kV"
        else:
            return "p.u."

    # --------------------------------------------------------------------------------------------------------
    # Communication methods
    async def read_async(self, mode: ReadMode = ReadMode.ALL) -> dict[str, ModbusValue | PandaPowerValue]:
        """
        Reads bus values from the configured source and updates the state.

        The method first reads the values via the base class, determines the base voltage from pandapower if needed, and then computes the complex voltage from ``vm_pu`` and ``va_degree``.

        ``vm_pu`` is interpreted as a voltage in volts if the value is greater than 2.
        In that case, conversion to kV or p.u. is performed.

        :param mode: Data source for the read access (Modbus, pandapower, or both)
        :type mode: ReadMode
        :return: Updated ``values`` dictionary
        :rtype: dict[str, ModbusValue | PandaPowerValue]
        """
        # Read Modbus and/or PandaPower values
        self.values = await super().read_async(mode)

        # Try to determine the base voltage from the PandaPower bus if it is not yet available
        if self.base_voltage < 0 :
            self.__try_get_base_voltage_from_pp() 

        # Determine the values from the internal dictionaries needed to calculate the complex voltage 
        vm_pu = self.values["vm_pu"].value
        va_degree = self.values["va_degree"].value

        if vm_pu is not None and va_degree is not None:
            # Check whether the value should be interpreted as voltage in 'V' or 'p.u.'
            # -> if 'vm_pu' magnitude is greater than 2, it is likely a voltage value in 'V'
            if vm_pu > 2:
                # PandaPower uses 'kV' and 'vm_pu' comes in 'V'. The base is 'kV'
                vm_pu = (vm_pu/1000)
                
                # If a base voltage could be determined, convert the value to p.u.  
                if self.base_voltage > 0:
                    vm_pu = (vm_pu/self.base_voltage)

            # Create the complex voltage value from the inputs
            self.__create_complex_voltage(vm_pu, va_degree)

            # If a visualization exists, store the values and update the visualization
            if self.VIS_INIT:
                # Update the visualization
                self.update_visualize()
         
        return self.values

    # --------------------------------------------------------------------------------------------------------
    # Bus helper methods
    def __create_complex_voltage(self, u_pu: float, u_angle_degree: float) -> complex:
        """
        Creates a complex voltage from magnitude and angle and stores it.

        Calculation:
            U = U_mag * (cos(phi) + j * sin(phi))

        If ``base_voltage`` is set, the value is scaled from p.u. to kV.

        :param u_pu: Voltage magnitude in p.u.
        :type u_pu: float
        :param u_angle_degree: Voltage angle in degrees
        :type u_angle_degree: float
        :return: Complex voltage (kV or p.u. depending on ``base_voltage``)
        :rtype: complex
        """
        # Angle in radians
        u_angle_rad = math.radians(u_angle_degree)

        # Real and imaginary part 
        real = u_pu * math.cos(u_angle_rad)
        imag = u_pu * math.sin(u_angle_rad)

        # Create the complex voltage (p.u.) as a value 
        u_komplex_pu = complex(real, imag) 

        # If a base voltage exists, u_value is in p.u. -> convert to kV
        if self.base_voltage > 0:
            self.voltage_complex = u_komplex_pu * self.base_voltage
        else:
            self.voltage_complex = u_komplex_pu

        return self.voltage_complex

    def __try_get_base_voltage_from_pp(self):
        """
        Tries to determine the nominal voltage (base voltage) in kV from the PandaPower network model (the ``vn_kv`` column of the bus DataFrame).
        The base voltage is used to convert values from 'p.u.' to 'kV'. If the lookup fails, the voltage remains represented in 'p.u.'.
        This is only performed once on the first call (``self.base_voltage`` is not read again).
        """
        try:
            # Nominal voltage in 'kV'
            base_voltage = self.pp_net.bus.at[self.net_index, "vn_kv"]
            self.base_voltage = base_voltage
        except:
            pass

    def update_visualize(self):
        """Updates the visualization including additional p.u. information."""
        super().update_visualize()

        # Add extra details about the current voltage if base voltage information is available
        text_pu = ""
        if self.base_voltage > 0:
            pu_complex = self.voltage_complex / self.base_voltage
            pu_perc = -(1-abs(pu_complex))*100
            text_pu = f" [{abs(pu_complex):.3f} p.u. | {pu_perc:.1f} % | {pu_complex:.3f}]"

        dpg.set_value(self.uuid_text, f"{self.value:.3f} {self.unit}{text_pu}") # pyright: ignore[reportArgumentType]

    # --------------------------------------------------------------------------------------------------------
    # Internal methods
    def __repr__(self):
        """Returns a compact text representation of the bus for debug output."""
        # If no complex voltage is available, output the number of internal values
        if np.isnan(self.voltage_complex.real) or np.isnan(self.voltage_complex.imag):
            return f"Bus [{self.name}] - Anzahl an internen 'Values' = {len(self.values)}"
        # If a base voltage is available or the magnitude is greater than 2,
        # then this is a voltage value in 'kV'
        elif self.base_voltage > 0: 
            return f"Bus [{self.name}]: {abs(self.voltage_complex):.2f} kV ({self.voltage_complex:.3f})"
        else:
            return f"Bus [{self.name}]: {abs(self.voltage_complex):.4f} p.u. ({self.voltage_complex:.3f})"