 # -*- coding: utf-8 -*-
"""
Bus.py
@author: Groß, Hendrik
"""
import pandapower as pp
from typing import List, Any
from .Base import BaseComponent

class Bus(BaseComponent):
    """Converts pandapower bus elements into ePHASORSIM bus objects."""

    worksheet_name: str | None  = "Bus"
    instruction_list: list[str] = ["Vmag", "Vang", "trip", "VangU"]

    def __init__(self, _id, _base_voltage, _vmag, _unit, _angle, _type):
        """
        https://opal-rt.atlassian.net/wiki/spaces/PEUD/pages/144438215/Bus
        
        :param _bus_id: DataFrame index used as bus ID (in pandapower all connected network elements also use this ID)
        :param _base_voltage: Base voltage value
        :param _vmag: Initial value of the bus voltage magnitude
        :param _unit: Use 'pu' for transmission networks and 'V' for distribution networks.
        :param _angle: Initial value of the bus voltage angle
        :param _type: Bus type
        """
        super().__init__(_id)
        self.base_voltage = _base_voltage
        self.vmag = _vmag
        self.unit = _unit
        self.angle = _angle
        self.type = _type

    def to_row(self) -> List[Any]:
        """Column order required by the ePHASORSIM template."""
        return [self.id, self.base_voltage, self.vmag, self.unit, self.angle, self.type]

    @classmethod
    def load_from_pp_net(cls, _pp_net: pp.pandapowerNet) -> List[object]:
        """Loads objects to convert from pandapower."""
        # A bus connected to ext_grid is considered a SLACK bus
        slack_buses  = [row["bus"] for _, row in _pp_net.ext_grid.iterrows()]
        
        bus_list: List[object] = []
        for idx, row in _pp_net.bus.iterrows():
            bus_list.append(cls(
                idx,                                
                row["vn_kv"]*1000,                  # kV -> V
                _pp_net.res_bus.vm_pu.at[idx],      # Power flow result
                "pu",                               
                _pp_net.res_bus.va_degree.at[idx],  # Power flow result
                "SLACK" if idx in slack_buses else "PQ"
                ))    
        return bus_list