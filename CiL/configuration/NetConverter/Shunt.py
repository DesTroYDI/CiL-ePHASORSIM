 # -*- coding: utf-8 -*-
"""
Shunt.py
@author: Groß, Hendrik
"""
import pandapower as pp
from typing import List, Any
from .Base import BaseComponent

class Shunt(BaseComponent):
    """Converts pandapower shunts into ePHASORSIM positive-sequence shunt objects."""
    model_typ: str | None           = "Positive-Sequence Shunt"
    worksheet_name: str | None      = "Shunt"
    instruction_list: list[str]     = ["Imag", "Iang", "P", "Q", "status"]
    prefix_dict: dict[str, str]     = {"SH": "shunt"}

    def __init__(self,_id,_status, _bus, _active_power,_reactive_power):
        """
        https://opal-rt.atlassian.net/wiki/spaces/PEUD/pages/144536035/Positive+Sequence+Shunt
        
        :param _id: ID (Name)
        :param _status: Connected/disconnected status
        :param _bus: ID of the connected bus
        :param _active_power: Active power
        :param _reactive_power: Reactive power
        """
        super().__init__(_id)
        self.status = _status
        self.bus = _bus
        self.active_power = _active_power
        self.reactive_power = _reactive_power

    def to_row(self) -> List[Any]:
        """Column order required by the ePHASORSIM template."""
        return [self.id, self.status, self.bus, self.active_power,self.reactive_power]
    
    @classmethod
    def load_from_pp_net(cls, _pp_net: pp.pandapowerNet) -> List[object]:
        """Loads objects to convert from pandapower."""
        return [
            cls(
                row["name"],
                int(row["in_service"]),
                row["bus"],
                row["p_mw"],
                row["q_mvar"]
            )
            for _, row in _pp_net.shunt.iterrows()
        ]