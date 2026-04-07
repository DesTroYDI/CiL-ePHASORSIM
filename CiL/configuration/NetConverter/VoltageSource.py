 # -*- coding: utf-8 -*-
"""
VoltageSource.py
@author: Groß, Hendrik
"""
import pandapower as pp
from typing import List, Any
from .Base import BaseComponent

class VoltageSource(BaseComponent):
    """
    Adds one positive-sequence voltage source to each SLACK bus (ext_grid entry).

    IDs are generated directly in ``load_from_pp_net()`` as "V{idx}" (e.g. "V0", "V1"), so no cleanup via ``prefix_dict`` is required.
    Series resistance and series reactance are set to 0 by default.
    """
    model_typ: str | None           = "Positive-Sequence Voltage Source "
    worksheet_name: str | None      = "Voltage Source"
    instruction_list: list[str]     = ["Vmag", "Vang", "resistance","reactance","Imag","Iang","Pout","Qout"]

    def __init__(self,_id,_bus, _voltage, _angle,_rs,_xs):
        """
        https://opal-rt.atlassian.net/wiki/spaces/PEUD/pages/144535932/Positive+Sequence+Voltage+Source
        
        :param _id: ID (Name)
        :param _bus: ID of the connected bus
        :param _voltage: Nominal voltage magnitude
        :param _angle: Voltage angle
        :param _rs: Series resistance
        :param _xs: Series reactance
        """
        super().__init__(_id)
        self.bus = _bus
        self.voltage = _voltage
        self.angle = _angle
        self.rs = _rs
        self.xs = _xs

    def to_row(self) -> List[Any]:
        """Column order required by the ePHASORSIM template."""
        return [self.id, self.bus, self.voltage, self.angle, self.rs, self.xs]
    
    @classmethod
    def load_from_pp_net(cls, _pp_net: pp.pandapowerNet) -> List[object]:
        """Loads objects to convert from pandapower."""
        return [
            cls(f"V{idx}", row["bus"], 1, 0, 0, 0)
            for idx, row in _pp_net.ext_grid.iterrows()
        ]