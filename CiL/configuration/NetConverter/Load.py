 # -*- coding: utf-8 -*-
"""
Load.py
@author: Groß, Hendrik
"""
import pandapower as pp
from typing import List, Any
from .Base import BaseComponent

class Load(BaseComponent):
    """
    Converts pandapower loads and static generators into ePHASORSIM positive-sequence constant-power load objects.

    Static generators (``sgen``) are modeled as negative loads to follow the load sign convention used in ePHASORSIM (consumer reference system).
    Scaling factors are converted to absolute values before this class is called.
    """
    model_typ: str | None           = "Positive-Sequence Constant Power Load"
    worksheet_name: str | None      = "Load"
    instruction_list: list[str]     = ["status", "P", "Q", "Imag", "Iang"]
    prefix_dict: dict[str, str]     = {"Ld": "load", "Gen": "sgen"}

    def __init__(self, _id, _status, _bus, _active_power, _reactive_power):
        """
        https://opal-rt.atlassian.net/wiki/spaces/PEUD/pages/144472923/Positive+Sequence+Load
        
        :param _id: ID (Name)
        :param _status: Initial connected/disconnected status
        :param _bus: Bus-ID
        :param _active_power: Active power
        :param _reactive_power: Reactive power (Q is positive for inductive loads and negative for capacitive loads)
        """
        super().__init__(_id)
        self.status = _status
        self.bus = _bus
        self.active_power = _active_power
        self.reactive_power = _reactive_power

    def to_row(self) -> List[Any]:
        """Column order required by the ePHASORSIM template."""
        return [self.id, self.status, self.bus, self.active_power, self.reactive_power]

    @classmethod
    def load_from_pp_net(cls, _pp_net: pp.pandapowerNet) -> List[object]:
        """Loads objects to convert from pandapower."""
        list_loads: List[object] = []
        # Loads: consumer reference system, values are taken unchanged
        list_loads += [
            cls(row["name"], int(row["in_service"]), row["bus"],
                row["p_mw"], row["q_mvar"] )
            for _, row in _pp_net.load.iterrows()
        ]
        
        # Static generators: generator reference system, therefore P and Q are negated
        list_loads += [
            cls(row["name"], int(row["in_service"]),row["bus"],
                -row["p_mw"], -row["q_mvar"])
            for _, row in _pp_net.sgen.iterrows()
        ]
        return list_loads
    