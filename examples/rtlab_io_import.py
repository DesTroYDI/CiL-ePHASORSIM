# -*- coding: utf-8 -*-
"""
rtlab_io_import.py

Imports the I/O pin configuration from a custom Excel CiL configuration file. 
To avoid manual Modbus value mapping by the user, this script can use the OPAL-RT Python API (https://opal-rt.atlassian.net/wiki/spaces/PRD/pages/143983801/RT-LAB+API+Documentation)
to create the mapping automatically from the Excel file. 

!!! Important: This script must be executed on an RT-LAB workstation from the RT-LAB Dashboard

@author: Groß, Hendrik
"""
import RtlabApi 


# Retrieve the active project to configure.
# TODO: replace with the corresponding RT-LAB API call, for example:
# active_project = RtlabApi.GetActiveProjects()
#
# Then import the I/O configuration and create the RT-LAB connection.
# TODO: add concrete API calls for:
# - ImportIOsConfiguration(...)
# - CreateConnection(...)
