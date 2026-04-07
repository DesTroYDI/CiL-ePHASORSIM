# -*- coding: utf-8 -*-
"""
NetConverter.py
@author: Groß, Hendrik
"""
from typing import Callable, Any
import os, PP2CHIL as PP2CHIL
from pandapower import to_pickle
from pandapower.plotting.plotly import simple_plotly
from pandapower.plotting.plotly import vlevel_plotly
from pandapower.plotting.plotly import pf_res_plotly
import dearpygui.dearpygui as dpg
from NetConverter.PPtoePHASORSIM import Converter, Pin

# For selecting I/O pins, a ready-made control is used
# Git-Repositories: https://github.com/xrcyz/dpg-swisscontrols.git
from .ListEditCtrl import DataGrid, listEditCtrl

"""
'NetConverter' provides the interface extension of the 'Converter' class. This control extends the GUI of 'OPALRT_CHIL' and
is shown after loading a pandapower network model.

The interface simplifies converting a pandapower network model into an Excel template for OPAL-RT.
"""
class NetConverter():
    
    # Global variables
    lec_io_pins: tuple[Callable[[], DataGrid], Callable[[Any], None]]    # ListEditControl with I/O settings

    # Constructor
    def __init__(self):
        """Initializes the visualization class that contains a converter object."""
        self.converter: Converter | None = None

    def create_gui(self):
        """
        Creates the interface for visualizing conversion of a pandapower network model into an OPAL-RT Excel template.

        :param self: Class object
        """
        # DataGrid for selectable objects
        dg_components = DataGrid(
            title="Object Selection",
            columns = ["Select", "Object ID", "Object Information"],
            dtypes = [DataGrid.CHECKBOX, DataGrid.TXT_TEXT, DataGrid.TXT_TEXT],
            defaults = [0, "", ""],
            combo_lists = [None, None, None]
        )
        
        # DataGrid for I/O pin input
        dg_io_pins = DataGrid(
            title="I/O Pins (* All bus voltages are added automatically as 'Outgoing', and all generators/loads as 'Incoming' for controllable elements and profiles)",
            columns = ["Type","Label", "Network Element","Instruction", "Objects"],
            dtypes = [DataGrid.COMBO, DataGrid.TXT_STRING,DataGrid.COMBO,DataGrid.COMBO,DataGrid.GRID],
            defaults = [1, "-",0, 0, dg_components],
            combo_lists = [["Incoming", "Outgoing"], None, 
                           Converter.get_components_name_list(), 
                           Converter.COMPONENTS[0].instruction_list, # The instruction combo list is read dynamically from the selected network element class
                           None] 
        )
        # Default I/O pin configuration
        # All bus voltages are always read as outgoing
        dg_io_pins.append([1, "bus_voltage_magnitude", 0, 0, dg_components]) 
        dg_io_pins.append([1, "bus_voltage_angle", 0, 1, dg_components.copy()])
        # Define controllable generator/load signals
        dg_io_pins.append([0, "set_p_gen_load", 2, 1, dg_components.copy()])
        dg_io_pins.append([0, "set_q_gen_load", 2, 2, dg_components.copy()])
        # Incoming data: active/reactive power of controllable load and generator objects
        dg_io_pins.append([0, "profile_set_p_gen_load", 2, 1, dg_components.copy()])
        dg_io_pins.append([0, "profile_set_q_gen_load", 2, 2, dg_components.copy()])
        # Incoming data: active/reactive power of remaining load and generator objects (needed only in the model)
        dg_io_pins.append([0, "ignore_profile_set_p_gen_load", 2, 1, dg_components.copy()])
        dg_io_pins.append([0, "ignore_profile_set_q_gen_load", 2, 2, dg_components.copy()])

        # Popup shown when no file has been selected yet
        with dpg.window(id="win_kein_pp_net", label="Notice",show=False, modal=True, autosize=True):
            dpg.add_text("No pickle file has been selected yet, or an error occurred while loading in pandapower!")
            dpg.add_separator()
            dpg.add_button(label="OK", width=75, callback=lambda: dpg.configure_item("win_kein_pp_net", show=False))

        # Add header font
        with dpg.tree_node(id="toolPPConverter", label="Network Model Converter (Excel v2.0)",show=False, default_open=True):
            with dpg.child_window(autosize_x=True, height=1800):
                with dpg.group(horizontal=True, width=0):
                    #----------------------------------------------------------------------------------------------------
                    # Window with settings for selecting and loading network models
                    with dpg.child_window(width=900, autosize_y=True):
                       
                        # Conversion information
                        items = [
                            ("Bus",             "Only PQ and SLACK buses. PV buses are not considered."),
                            ("Line",            ""),
                            ("Load",            "Scaling is reset"),
                            ("Switch",          "All network elements are converted to a bus-bus connection if not already present."),
                            ("Shunt",           ""),
                            ("Static Generator","Interpreted as negative 'Load'; scaling is reset"),
                            ("External Grid",   "Converted to 'Voltage Source' and considered at SLACK buses"),
                            ("Two-winding Transformer", ""),
                        ]
                        dpg.add_text("This conversion considers only the following pandapower data structures:")
                        with dpg.table(header_row=True, borders_innerH=True, borders_outerH=True, borders_innerV=True, borders_outerV=True):
                            dpg.add_table_column(label="Pandapower DataFrame")
                            dpg.add_table_column(label="Note")
                            for name, hint in items:
                                with dpg.table_row():
                                    dpg.add_text(name)
                                    dpg.add_text(hint)
                        
                        #----------------------------------------------------------------------------------------------------
                        # Export settings / I-O pins
                        with dpg.child_window(autosize_x=True, autosize_y=True):
                            dpg.add_text("--- Export Excel-Template Einstellungen ---")
                            with dpg.group(horizontal=True, width=0):
                                dpg.add_button(label="Open file explorer",callback=PP2CHIL.call_file_dialog, user_data=[3,"export_folder"])
                                dpg.add_input_text(id="export_folder", hint="Folder for ePHASORSIM model output (ExcelTemplate.xlsx) and converted network model (NetworkModel.p)",width=-1)
                            with dpg.group(horizontal=True, width=0):
                                dpg.add_button(label="Run: export network model and ePHASORSIM model", callback=self.export_pp_ephasorsim_net)
                                dpg.bind_item_theme(dpg.last_item(), "theme_execute")
                                dpg.add_loading_indicator(id="loading_indicator_pp_conversion", show=False)
                                dpg.add_text(id="pp_conversion_status", default_value="No conversion executed!", color=(255, 0, 0))
                            self.lec_io_pins = listEditCtrl(dpg.generate_uuid(),grid=dg_io_pins)

                    #----------------------------------------------------------------------------------------------------
                    # Window with network model information and optional browser view
                    with dpg.child_window(autosize_x=True, autosize_y=True):
                        dpg.add_text("--- Network Model Information ---")
                        # Select which pandapower view to display (normal or power flow results)
                        with dpg.group(horizontal=True, width=0):                        
                            dpg.add_text("Display in browser:")
                            dpg.add_button(label="Network Model", height=30, callback=self.view_pp_net, user_data="simple")
                            dpg.add_button(label="Voltage Levels", height=30, callback=self.view_pp_net, user_data="vlevel")
                            dpg.add_button(label="Power Flow", height=30, callback=self.view_pp_net, user_data="res")
                        
                        # Table with network model information
                        dpg.add_text("Network model information:")
                        with dpg.table(header_row=True, resizable=True,policy=dpg.mvTable_SizingStretchProp) as table_id:

                            dpg.add_table_column(label="Object Type")
                            dpg.add_table_column(label="Unit")
                            dpg.add_table_column(label="Value")

                            # Netzknoten
                            with dpg.table_row():
                                dpg.add_text(f"Buses")
                                dpg.add_text(f"Count [n]")
                                dpg.add_text(id="idBus",default_value="-")
                            # Netzleitungen
                            with dpg.table_row():
                                dpg.add_text(f"Lines")
                                dpg.add_text(f"Length [km]")
                                dpg.add_text(id="idLine",default_value="-")
                            # Transformatoren
                            with dpg.table_row():
                                dpg.add_text(f"Transformers")
                                dpg.add_text(f"Count [n] / Total rated power [MVA]")
                                dpg.add_text(id="idTrafo",default_value="-")
                            # Loads
                            with dpg.table_row():
                                dpg.add_text(f"Loads")
                                dpg.add_text(f"Count [n] / Total power [MW]")
                                dpg.add_text(id="idLoad",default_value="-")
                            # Erzeuger
                            with dpg.table_row():
                                dpg.add_text(f"Generators")
                                dpg.add_text(f"Count [n] / Total rated power [MW]")
                                dpg.add_text(id="idGen",default_value="-")
                                         
    def view_pp_net(self, sender, app_data, user_data):
        """
        Displays the network model in an external browser. Display settings are fixed.

        :param self: Class object
        :param user_data: Mode defining how the network model should be displayed
        """
        # Check whether a converter has been loaded
        if self.converter is None:
            print("CONVERTER_NONE - Network visualization unavailable. No converter loaded!")
            return

        # Plot only the network model
        if user_data == "simple":
            simple_plotly(self.converter.pp_net, map_style="open-street-map")
        # Display by voltage levels
        elif user_data == "vlevel":
            vlevel_plotly(self.converter.pp_net, map_style="open-street-map")
        # Display power flow results
        elif user_data == "res":
            pf_res_plotly(self.converter.pp_net, map_style="open-street-map")

    def load_pp_converter(self,pickle_file) -> tuple[bool, str]:
        """Loads the pandapower converter object."""
        str_return = ""
        bool_return = False
        # Load the network model so additional settings can be configured
        try:
            # Pass pickle file to converter (and pandapower)
            self.converter = Converter()
            self.converter.load_pp_net_from_pickle(pickle_file)
            
            # Check whether the network model was actually loaded
            if self.converter.pp_net is None:
                raise Exception("PP_NET_NONE - Error while loading pandapower network model")            

            # Import successful
            str_return ="Network model loaded successfully"
            dpg.configure_item("import_status", color=(0, 255, 0))

            _pp_net = self.converter.pp_net
            # Pass to ListEditControl for I/O configuration
            _,func_pp_net = self.lec_io_pins      
            func_pp_net(_pp_net)
            bool_return = True

            # Fill statistics if objects with these IDs exist
            try:
                dpg.set_value("idBus", len(_pp_net.bus))
                dpg.set_value("idLine", f"{_pp_net.line.length_km.sum():.2f} km")
                dpg.set_value("idTrafo", f"{len(_pp_net.trafo)} / {_pp_net.trafo.sn_mva.sum():.2f} MVA")
                dpg.set_value("idLoad", f"{len(_pp_net.load)} / {_pp_net.load.p_mw.sum():.2f} MW")
                dpg.set_value("idGen", f"{len(_pp_net.sgen)} / {_pp_net.sgen.p_mw.sum():.2f} MW")
            except:
                print("DPG controls are not reachable")
        except Exception as e:
            # Reset
            str_return = str(e)
        return (bool_return, str_return)

    def export_pp_ephasorsim_net(self):
        """
        Converts the pandapower network model into an Excel template and stores both the ePHASORSIM network model (*.xlsx)
        and the converted pandapower network model (*.p) in the selected folder.
        """
        dpg.configure_item("loading_indicator_pp_conversion", show=True)  # Loading indicator
        dpg.configure_item("pp_conversion_status", default_value="Running...")
        _error = ""

        if self.converter is None or self.converter.pp_net is None:
            _error = "Converter or pandapower network model is 'None'"
        else:
            # Get output path; if empty, use current working directory
            export_folder = dpg.get_value("export_folder")
            if export_folder is None or export_folder == "":
                export_folder = os.getcwd()
            try:
                # Define I/O pins
                _list_pins = []
                grid: DataGrid = self.lec_io_pins[0]()
            
                # Transpose the matrix with zip()
                _data_rows = list(zip(*grid.data))
                for _, _data_row in enumerate(_data_rows):
                    _pin_list = [] # Pins specified in the configuration
                    _instruction = ""

                    # Determine instruction
                    _component_name = grid.combo_lists[2][_data_row[2]] # pyright: ignore[reportOptionalSubscript]
                    for component in Converter.COMPONENTS:
                        if component.__name__ == _component_name:
                            _instruction = component.instruction_list[_data_row[3]]
                            break

                    # Export network-element objects
                    for _,_row_component in enumerate(list(zip(*_data_row[4].data))):
                        if _row_component[0] == True:    # Component pin should be exported
                            _pin_list.append(f"{_row_component[1]}/{_instruction}")    # v2.0 instruction format (object ID/instruction)

                    _pin = Pin(_data_row[0],_data_row[1],_pin_list)       # Pin definition
                    _list_pins.append(_pin)                                # List of pin definitions

                # Create Excel file and pass it to DPG control 'pp_converted_net' if available
                self.converter.create_excel_template(export_folder,_list_pins)
                if dpg.does_item_exist("text_excel_template_file"):
                    dpg.set_value("text_excel_template_file",self.converter.excel_file)
                # Export pandapower network model and pass it to DPG control 'pp_converted_net' if available
                net_name = "NetworkModel"
                if self.converter.pp_net.name is not None and self.converter.pp_net.name != "":
                    net_name = self.converter.pp_net.name
                
                sPPNetPath = f"{export_folder}\\{net_name}.p"
                to_pickle(self.converter.pp_net, sPPNetPath)
                if dpg.does_item_exist("pp_converted_net"):
                    dpg.set_value("pp_converted_net",sPPNetPath)
                
                dpg.configure_item("loading_indicator_pp_conversion", show=False) 
                dpg.configure_item("pp_conversion_status", default_value="Export successful!")
                dpg.configure_item("pp_conversion_status", color=(0, 255, 0))
                return
            except Exception as e:
                _error = str(e)
        # Reset
        dpg.configure_item("loading_indicator_pp_conversion", show=False)  
        dpg.configure_item("pp_conversion_status", default_value=_error)
        dpg.configure_item("pp_conversion_status", color=(255, 0, 0))