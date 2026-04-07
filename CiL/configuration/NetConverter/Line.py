 # -*- coding: utf-8 -*-
"""
Line.py
@author: Groß, Hendrik
"""
import numpy as np
import pandapower as pp
from typing import List, Any
from .Base import BaseComponent

class Line(BaseComponent):
    """
    Converts pandapower lines into ePHASORSIM positive-sequence line objects.

    Parameters are converted from physical units (ohm, nF) into per-unit values on the network base
    (``V_base`` of the from bus, `S_base` = ``pp_net.sn_mva``). Parallel lines and line capacitances
    (Pi model) are considered.
    """
    model_typ: str | None           = "Positive-Sequence Line"
    worksheet_name: str | None      = "Line"
    instruction_list: list[str]     = ["faulty", "fault_distance_factor", "status", "Imag0", "Iang0", "Imag1", "Iang1",
                                        "P0","Q0","P1","Q1","PL","QL","resistance","reactance","capacitance"]
    prefix_dict: dict[str, str]     = {"Ln": "line"}

    def __init__(self, _id, _status, _from_bus, _to_bus, _resistance, _reactance, _capacitive):
        """
        https://opal-rt.atlassian.net/wiki/spaces/PEUD/pages/144536130/Positive+Sequence+Line
        
        :param _id: Line ID (name)
        :param _status: Connected/disconnected status
        :param _from_bus: Sending bus
        :param _to_bus: Receiving bus
        :param _resistance: Series resistance
        :param _reactance: Series reactance (2*pi*f*L)
        :param _capacitive: Capacitive term (2*pi*f*C)
        """
        super().__init__(_id)
        self.status = _status
        self.from_bus = _from_bus
        self.to_bus = _to_bus
        self.resistance = _resistance
        self.reactance = _reactance
        self.capacitive = _capacitive

    def to_row(self) -> List[Any]:
        """Column order required by the ePHASORSIM template."""
        return [self.id, self.status, self.from_bus, self.to_bus, self.resistance, self.reactance, self.capacitive]

    @classmethod
    def load_from_pp_net(cls, _pp_net: pp.pandapowerNet) -> List[object]:
        """Loads objects to convert from pandapower."""
        _line_list = [] 
        for _, row in _pp_net.line.iterrows():
            from_bus = row["from_bus"]
            # Build per-unit base values from the nominal voltage on the sending side.
            # With ``vn_kv`` in kV and ``sn_mva`` in MVA, ``Z_base`` is directly in ohm.
            V_base = _pp_net.bus.at[from_bus, "vn_kv"]      # kV
            Z_base = V_base**2 / _pp_net.sn_mva             # Ohm  (Z = V²/S)
            Y_base = 1 / Z_base                             # S

            length = row["length_km"]
            # Parallel lines divide the series impedance and add the shunt capacitance.
            parallel = row.get("parallel", 1)

            # Series impedance: total resistance/reactance for the line section
            R_ohm = row["r_ohm_per_km"] * length / parallel 
            X_ohm = row["x_ohm_per_km"] * length / parallel 
            # Convert physical ohm values to per-unit.
            R_pu = R_ohm / Z_base
            X_pu = X_ohm / Z_base

            # Shunt susceptance: the Pi model distributes B equally to both ends.
            C = row.get("c_nf_per_km", 0.0) * length * 1e-9 * parallel  # F
            # B = wC with w = 2*pi*f. Half of the shunt part per line end is used.
            B = 2 * np.pi * _pp_net.f_hz * C
            B_pu = (B / 2) / Y_base if C > 0 else 0.0  

            # Return all pandapower elements as a list
            _line_list.append(cls(
                row["name"],
                int(row["in_service"]),
                from_bus,
                row["to_bus"],
                R_pu, X_pu, B_pu
            )) 
        return _line_list