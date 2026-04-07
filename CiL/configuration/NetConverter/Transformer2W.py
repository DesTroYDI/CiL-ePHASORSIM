 # -*- coding: utf-8 -*-
"""
Transformer2W.py
@author: Groß, Hendrik
"""
import math
import pandas as pd
import pandapower as pp
from typing import List, Any
from .Base import BaseComponent

class Transformer(BaseComponent):
    """
        Converts pandapower two-winding transformers into ePHASORSIM positive-sequence 2W transformer objects.

        Three parameter groups are calculated independently:
            - Short-circuit impedance (R, X) from ``vkr_percent`` / ``vk_percent``
            - Off-nominal tap ratios (``ratio_w1``, ``ratio_w2``) from tap position and tap step
            - Magnetizing admittance (``G_mag``, ``B_mag``) from iron losses and no-load current
        All values are converted to per-unit on the network base (``sn_mva``).
    """
    model_typ: str | None           = "Positive-Sequence 2W-Transformer"
    worksheet_name: str | None      = "Transformer"
    instruction_list: list[str]     = ["rW1","rW2","Imag1","Imag2","Iang1","Iang2"]
    prefix_dict: dict[str, str]     = {"Trf": "trafo"}

    def __init__(self, _id, _status, _from_bus, _to_bus, _resistance, _reactance, _gmag, _bmag, _ratio_w1,_ratio_w2,_phase_shift):
        """
        https://opal-rt.atlassian.net/wiki/spaces/PEUD/pages/144536079/Positive+Sequence+Transformer
        
        :param _id: ID (Name)
        :param _status: Connected/disconnected status
        :param _from_bus: Primary bus ID
        :param _to_bus: Secondary bus ID
        :param _resistance: Resistance between primary and secondary bus
        :param _reactance: Reactance between primary and secondary bus
        :param _fG_gmagmag: Magnetizing conductance
        :param _bmag: Magnetisierungssuszeptanz
        :param _ratio_w1: Primary off-nominal ratio
        :param _ratio_w2: Secondary off-nominal ratio
        :param _fPS: Voltage between primary and secondary bus
        """
        super().__init__(_id)
        self.status = _status
        self.from_bus = _from_bus
        self.to_bus = _to_bus
        self.resistance = _resistance
        self.reactance = _reactance
        self.gmag = _gmag
        self.bmag = _bmag
        self.ratio_w1 = _ratio_w1
        self.ratio_w2 = _ratio_w2
        self.phase_shift = _phase_shift

    def to_row(self) -> List[Any]:
        """Column order required by the ePHASORSIM template."""
        return [self.id, self.status, self.from_bus, self.to_bus, self.resistance, self.reactance, self.gmag, self.bmag, self.ratio_w1, self.ratio_w2, self.phase_shift]
    
    @classmethod
    def load_from_pp_net(cls, _pp_net: pp.pandapowerNet) -> List[object]:
        """Loads objects to convert from pandapower."""
        _trafo_list = []
        for _, row in _pp_net.trafo.iterrows():
            # Compute each parameter group separately according to the template model.
            R_pu, Xl_pu         = Transformer._get_short_circuit_impedance_pu(row,_pp_net.sn_mva)
            ratio_w1, ratio_w2  = Transformer._get_ratios(row)
            gmag, bmag          = Transformer._get_magnetizing_admittance(row,_pp_net.sn_mva)

            _trafo_list.append(cls(
                row["name"],
                int(row["in_service"]),
                row["hv_bus"],
                row["lv_bus"],
                R_pu, Xl_pu,
                gmag, bmag,         
                ratio_w1, ratio_w2, 
                row["shift_degree"] 
            )) 
        return _trafo_list
    
    @staticmethod
    def _get_short_circuit_impedance_pu(_trafo, _base_sn):
        """
        Computes series R and X in per-unit on the network base.

        Formula (scaled from transformer base to network base):
            ``R_pu`` = (vkr_percent / 100) * (S_base / S_trafo)
            ``X_pu`` = (vk_percent  / 100) * (S_base / S_trafo)

        :param _trafo: Data row of the pandapower transformer
        :param _base_sn: ``sn_mva`` des pandapower-Netzmodells
        """
        sn_trafo    = _trafo["sn_mva"]
        vk_percent  = _trafo.get("vk_percent", 0.0)
        vkr_percent = _trafo.get("vkr_percent", 0.0)

        if sn_trafo > 0:
            # Scale transformer nameplate per-unit values to the network base MVA.
            scale = _base_sn / sn_trafo
            R_pu = (vkr_percent / 100) * scale
            Xl_pu = (vk_percent / 100) * scale
        else:
            # Safeguard against invalid nameplate data.
            R_pu = Xl_pu = 0.0

        return R_pu, Xl_pu

    @staticmethod
    def _get_ratios(_trafo):
        """
        Computes off-nominal tap ratios for HV (``ratio_w1``) and LV side (``ratio_w2``).

        ``tap_change_pu`` = (tap_pos * tap_step_percent) / 100

        The ratio on the tapped side is set to 1 + ``tap_change_pu``, the other side to 1.0.
        
        :param _trafo: Data row of the pandapower transformer
        """
        ratio_w1 = ratio_w2 = 1.0

        if "tap_side" in _trafo and not pd.isna(_trafo["tap_side"]):
            # Convert tap position and step size to a relative ratio change.
            tap_pos = _trafo.get("tap_pos", 0)
            tap_percent = _trafo.get("tap_step_percent", 0)
            tap_change_pu = (tap_pos * tap_percent) / 100 
            
            if _trafo["tap_side"] == "hv":
                ratio_w1 = 1.0 + tap_change_pu
            elif _trafo["tap_side"] == "lv":
                ratio_w2 = 1.0 + tap_change_pu
            else:
                # Fallback: apply the same ratio to both sides.
                ratio_w1 = ratio_w2 = 1.0 + tap_change_pu
        
        return ratio_w1, ratio_w2

    @staticmethod
    def _get_magnetizing_admittance(_trafo, _base_sn):
        """
        Computes magnetizing conductance ``G_mag`` and susceptance ``B_mag`` in per-unit.

            ``G_mag`` = P_fe [MW] / S_base          (Eisenverluse, V=1 p.u. angenommen)
            ``B_mag`` = sqrt(i0_pu_network^2 - G_mag^2)

        Falls i0^2 < G^2 (numerischer Randfall), wird ``B_mag`` auf ``i0_pu_network`` gesetzt.

        :param _trafo: Data row of the pandapower transformer
        :param _base_sn: ``sn_mva`` des pandapower-Netzmodells
        """
        if "pfe_kw" in _trafo:
            # Convert no-load iron losses from kW to MW and then to per-unit conductance.
            G_mag = (_trafo["pfe_kw"] / 1000) / _base_sn
        else:
            G_mag = 0.0
 
        if "i0_percent" in _trafo:
            # Convert no-load current from transformer base to per-unit on the network base.
            i0_pu_network = (_trafo["i0_percent"] / 100) * (_trafo["sn_mva"] / _base_sn)
            if i0_pu_network**2 > G_mag**2:
                # Enforce B = sqrt(I0^2 - G^2) according to admittance magnitude relation.
                B_mag = math.sqrt(i0_pu_network**2 - G_mag**2)
            else:
                # Numerical fallback for near-limit cases.
                B_mag = i0_pu_network
        else:
            B_mag = 0.0
 
        return G_mag, B_mag