 # -*- coding: utf-8 -*-
"""
Switch.py
@author: Groß, Hendrik
"""
import pandapower as pp
from typing import List, Any
from .Base import BaseComponent

class Switch(BaseComponent):
    """
    Converts pandapower switches into ePHASORSIM switch objects (bus-bus).

    ePHASORSIM supports only bus-bus switches. Non-bus switches are transformed into
    a bus-bus topology earlier in the conversion pipeline. Therefore all entries in
    ``pp_net.switch`` here already use et="b".
    """
    worksheet_name: str | None      = "Switch"
    instruction_list: list[str]     = ["status", "Imag", "Iang"]
    prefix_dict: dict[str,str]      = {"SW": "switch"}

    def __init__(self,_id,_status, _from_bus, _to_bus):
        """
        https://opal-rt.atlassian.net/wiki/spaces/PEUD/pages/144472544/Switch
        
        :param _id: ID (Name)
        :param _status: Connected/disconnected status
        :param _from_bus: ID of the first bus
        :param _to_bus: ID of the second bus
        """
        super().__init__(_id)
        self.status = _status
        self.from_bus = _from_bus
        self.to_bus = _to_bus

    def to_row(self) -> List[Any]:
        """Column order required by the ePHASORSIM template."""
        return [self.from_bus, self.to_bus, self.id, int(self.status)]

    @classmethod
    def load_from_pp_net(cls, _pp_net: pp.pandapowerNet) -> List[object]:
        """Loads objects to convert from pandapower."""
        return [
            cls(
                row["name"],
                row["closed"],
                row["bus"],
                row["element"]
            )
            for _, row in _pp_net.switch.iterrows()
        ]