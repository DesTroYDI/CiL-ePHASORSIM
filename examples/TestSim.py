# -*- coding: utf-8 -*-
"""
@author: Groß, Hendrik
"""
import logging
import pandapower as pp

# Load Grid Element classes
from CiL.Bus import Bus
from CiL.Transformer2W import Transformer2W

# Controller/Dashboard/Alert classes
from CiL.Controller import Controller
from CiL.dashboard.Alert import VoltageBandAlert
from CiL.dashboard.Dashboard import Dashboard

# Logging configuration
logging.getLogger("pymodbus").setLevel(logging.WARNING)
logging.getLogger("numba").setLevel(logging.WARNING)
logging.getLogger("pymodbus.logging").setLevel(logging.WARNING)

folder = r"D:\Downloads"
# load pandapower network
file_pp_net = f"{folder}\\MV_Oberrhein_2026.p"
net = pp.from_pickle(file_pp_net,True)

# load CiL configuration
file_chil_cfg = f"{folder}\\CiL-Configuration.xlsx"
lst_elements = Controller.load_cfg_from_excel(file_chil_cfg)
lst_alerts = []

# Create alerts for all buses in the network
for element in lst_elements:
    if element.df_pp == "bus":
        lst_alerts.append(VoltageBandAlert(element,0.97,1.03))

# Run Dashboard
chil = Controller("10.0.0.114",502,net, lst_elements)
dashboard = Dashboard(chil,lst_alerts, [Bus])
dashboard.start()
