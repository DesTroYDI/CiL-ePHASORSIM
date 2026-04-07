# -*- coding: utf-8 -*-
"""
rtlab_io_import.py

Import der I/O-Pin-Konfiguration aus der eigens definierten Excel-CiL-Konfigrationsdatei. 
Um zu verhindern, dass der Benutzer die Konfiguration der Modbus-Werte selber übernehmen muss, kann dieses Skript mittel der OPAL-RT Python-API (https://opal-rt.atlassian.net/wiki/spaces/PRD/pages/143983801/RT-LAB+API+Documentation)
die Verknüpfung automatisiert aus der Excel-Datei hergestellen. 

!!! Wichtig: Dieses Skript muss in RT-LAB-Rechner im RT-LAB Dashboard ausgeführt werden

@author: Groß, Hendrik
"""
import RtlabApi 


# Aktives Projekt zur Konfiguration holen
GetActiveProjects --> TODO: Aktives Projekt holen

ImportIOsConfiguration

CreateConnection???