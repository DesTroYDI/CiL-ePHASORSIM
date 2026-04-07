# -*- coding: utf-8 -*-
"""
OPALRT_CHIL.py
@author: Groß, Hendrik
"""
# Configuration variables
WINDOW_TITLE = "Controller Hardware-in-the-Loop (C-HiL) - Configuration" # Window title
WINDOW_ICON = ".\\Ressources\\iconH.ico"                                 # Window icon

# Font IDs
TOOL_FONT = "tool_font"
HEADER_FONT = "header_font"

import GUI.CiLGenerator as cgen         # CHIL generator
import GUI.PPNetConverter as nmc         # NMC - network model converter
import dearpygui.dearpygui as dpg        # Required for visualization

# Use the Tkinter file dialog because the built-in DearPyGui file dialog triggers an error in Python's global threading shutdown:
#Exception ignored on threading shutdown:
#Traceback (most recent call last):
#  File "C:\Python\Python313\Lib\threading.py", line 1524, in _shutdown
#    if _main_thread._handle.is_done() and _is_main_interpreter():
#SystemError: <method 'is_done' of '_thread._ThreadHandle' objects> returned a result with an exception set
import tkinter as tk
from tkinter import filedialog

# ----------------------------------------------------------------
# Methods required for the GUI
# The class definition for external integration is located below the methods

def call_file_dialog(sender, app_data, user_data):
    """
    Opens a file dialog in different variants depending on the ``user_data`` parameter.
    ``user_data`` passes an array with two values:
        - int value indicating the file type
        - name of the DPG text box
    
    Dialog modes:
        0 - Search for an Excel file
        1 - Search for a PandaPower pickle file
        2 - Save an Excel file
        3 - Select a folder
        4 - Save a CSV file
    """
    root = tk.Tk()
    root.withdraw()

    # Variables
    file_path = None
    file_type = user_data[0]
    txtbox_name = user_data[1]

    # Mode 0: File dialog for selecting an Excel network model
    if file_type==0:
        file_path = filedialog.askopenfilename(title="Select Excel file", 
                                                filetypes=[("Excel file (*.xlsx)","*.xlsx")])

    # Mode 1: File dialog for selecting a pickle network model
    if file_type==1:
        file_path = filedialog.askopenfilename(title="Select pandapower network model", 
                                                filetypes=[("Pickle file (*.p)","*.p")])
    
    # Mode 2: File dialog for saving the Excel template
    elif file_type==2:
        file_path = filedialog.asksaveasfilename(title="Save Excel file", 
                                                filetypes=[("Excel file (*.xlsx)","*.xlsx")],
                                                defaultextension=[("Excel file (*.xlsx)","*.xlsx")]) # pyright: ignore[reportArgumentType]
    
    # Mode 3: File dialog for selecting a folder
    elif file_type==3:
        file_path = filedialog.askdirectory(title="Select folder")

    # Mode 4: File dialog for saving a CSV file
    elif file_type==4:
        file_path = filedialog.asksaveasfilename(title="Save CSV file", 
                                                filetypes=[("CSV file (*.csv)","*.csv")],
                                                defaultextension=[("CSV file (*.csv)","*.csv")]) # pyright: ignore[reportArgumentType]

    # Set the file path in the text widget
    if file_path is not None and file_path != "":
        dpg.set_value(txtbox_name, file_path)

def center_window(window_name: str):
    """
    Function that centers a popup in the middle of the window
    
    :param _name: Window name
    :type _name: str
    """
    dpg.configure_item(window_name, show=True)

    # Viewport size
    vp_width: int = dpg.get_viewport_width()
    vp_height: int = dpg.get_viewport_height()

    # Window size
    win_width = dpg.get_item_width(window_name)
    win_height = dpg.get_item_height(window_name)
    if win_width is None or win_height is None:
        return
    
    # Set centered position
    dpg.set_item_pos(
        window_name,
        [(vp_width - win_width) // 2,
        (vp_height - win_height) // 2]
    )

def load_pp_net_converter(sender, app_data, user_data):
    """ 
    Loads the visual for configuring the pandapower network model conversion.
    """
    # Names of the DPG import status elements
    name_load_inc = "loading_indicator"
    name_load_status = "import_status"
    
    # Initialize status variables
    str_text = "No network model has been loaded yet!"
    color_text = (255, 0, 0)
    load_pp = False

    # Update the widgets
    dpg.configure_item(name_load_inc, show=True)
    dpg.configure_item(name_load_status, default_value="Running...")
    
    # Check whether a file is present at all
    pickle_file = dpg.get_value("text_pickle_file")
    if not (pickle_file is None or pickle_file == ""):
        load_pp, str_text = pp_net_converter.load_pp_converter(pickle_file)
    
    # Evaluate the result
    if load_pp == False:
        # Show popup
        dpg.configure_item("win_kein_pp_net", show=True)
        center_window("win_kein_pp_net")

        dpg.set_value("idBus", "-")
        dpg.set_value("idLine", "-")
        dpg.set_value("idTrafo", "-")
        dpg.set_value("idLoad", "-")
        dpg.set_value("idGen", "-")
        pp_net_converter.converter = None
    else:
        color_text = (0, 255, 0)

    dpg.configure_item(name_load_status, color=color_text)
    dpg.configure_item(name_load_status, default_value=str_text)
    dpg.configure_item(name_load_inc, show=False)  
    # Hide the "tool window"
    dpg.configure_item("toolPPConverter", show=load_pp)

def load_cil_generator(sender, app_data, user_data):
    """ 
    Loads the visual for configuring the pandapower network model conversion.
    """
    # Determine the DPG import status elements and initialize them
    name_load_inc = "loading_indicator2"
    name_load_status = "import_status2"
    str_text = "No ePHASORSIM model or pandapower network model has been loaded yet!"
    color_text = (255,0,0)
    load_chil = False

    dpg.configure_item(name_load_inc, show=True)
    dpg.configure_item(name_load_status, default_value="Running...")
    
    # Check whether a file is present at all
    excel_file = dpg.get_value("text_excel_template_file")
    pp_file = dpg.get_value("pp_converted_net")
    if not ((excel_file is None or excel_file == "") or (pp_file is None or pp_file == "")):
        load_chil, str_text = chil_generator.load_ephasorsim_chil(excel_file,pp_file)

    # Evaluate the result
    if load_chil == False:
        dpg.configure_item("win_kein_ephasorsim_net", show=True)
        center_window("win_kein_ephasorsim_net")
        chil_generator.chil_object = None
    else:
        color_text = (0, 255, 0)

    # Stop the loading indicator
    dpg.configure_item(name_load_status, default_value=str_text)
    dpg.configure_item(name_load_inc, show=False)  
    dpg.configure_item(name_load_status, color=color_text)
    # Hide the "tool window"
    dpg.configure_item("toolCiLGenerator", show=load_chil)

def create_header(ctrl_height):
    """
    Creates a static header with logo and information about the master's project.
    """    
    # Register fonts and apply them globally
    with dpg.font_registry():
        global_font = dpg.add_font("C:/Windows/Fonts/calibri.ttf", 14)
        dpg.add_font("C:/Windows/Fonts/calibrib.ttf", 16, tag=TOOL_FONT)
        dpg.add_font("C:/Windows/Fonts/calibrib.ttf", 24, tag=HEADER_FONT)
    dpg.bind_font(global_font)
    
    # Load the THM logo
    with dpg.texture_registry():    
        img_width, img_height, _, img_data = dpg.load_image("Ressources\\THM2.png")
        dpg.add_static_texture(img_width, img_height, img_data,tag="thm_logo_tex")

    # Reduce the logo height so there is some padding above and below
    logo_height = max(ctrl_height - 12, 36)
    logo_width = int(img_width * (logo_height / img_height))

    with dpg.child_window(autosize_x=True, height=ctrl_height, border=False,no_scrollbar=True):
        with dpg.group(horizontal=True):
            # Logo on the left
            with dpg.child_window(width=logo_width + 20, auto_resize_y=True, border=False):
                dpg.add_spacer(width=12)
                dpg.add_image("thm_logo_tex", width=logo_width, height=logo_height)

            with dpg.child_window(tag="header_text_container", auto_resize_x=True, auto_resize_y=True, border=False):
                dpg.bind_item_theme("header_text_container", "theme_header_compact")
                dpg.add_spacer(height=2)
                with dpg.group(horizontal=True):
                    with dpg.group():
                        dpg.add_text("Masterprojektarbeit", color=(190, 190, 200))
                        dpg.bind_item_font(dpg.last_item(), TOOL_FONT)
                        dpg.add_text("Controller Hardware-in-the-Loop (C-HiL)", color=(235, 235, 245))
                        dpg.bind_item_font(dpg.last_item(), HEADER_FONT)

                    dpg.add_spacer(width=12)
                    with dpg.group():
                        label_width = 120
                        with dpg.group(horizontal=True):
                            with dpg.child_window(width=label_width, auto_resize_y=True, border=False):
                                dpg.add_text("Thema:", color=(170, 170, 180))
                                dpg.bind_item_font(dpg.last_item(), TOOL_FONT)
                            dpg.add_text("Implementierung eines C-Hil Teststands mit einem OPAL-RT OP4510")
                            dpg.bind_item_font(dpg.last_item(), TOOL_FONT)

                        with dpg.group(horizontal=True):
                            with dpg.child_window(width=label_width, auto_resize_y=True, border=False):
                                dpg.add_text("Autor:", color=(170, 170, 180))
                                dpg.bind_item_font(dpg.last_item(), TOOL_FONT)
                            dpg.add_text("Hendrik Groß")
                            dpg.bind_item_font(dpg.last_item(), TOOL_FONT)

                        with dpg.group(horizontal=True):
                            with dpg.child_window(width=label_width, auto_resize_y=True, border=False):
                                dpg.add_text("Matrikelnummer:", color=(170, 170, 180))
                                dpg.bind_item_font(dpg.last_item(), TOOL_FONT)
                            dpg.add_text("5564543")
                            dpg.bind_item_font(dpg.last_item(), TOOL_FONT)

def create_themes():
    """Creates professional themes for the GUI"""
    # Define the global theme
    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (35, 35, 45))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (50, 50, 65))
            dpg.add_theme_color(dpg.mvThemeCol_Button, (70, 130, 180))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (100, 160, 210))
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 5)
            dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 3)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 6, 6)     # Spacing between widgets
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 6)    # Inner padding of buttons/inputs
    dpg.bind_theme(global_theme)

    # Button themes
    with dpg.theme(tag="theme_execute"):
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, (80, 180, 120))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (100, 200, 140))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (60, 160, 100))

    # Tighter spacing only for header texts
    with dpg.theme(tag="theme_header_compact"):
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 20, -6)

def create_gui():
    # Main window
    with dpg.window(tag="win1"):
        dpg.add_texture_registry(label="texture_container", tag="texture_container")    # Container for all textures
                
        # Create themes
        create_themes()

        # Create header
        create_header(72)

        # Create the TabBar control for the tools
        with dpg.tab_bar(id="tab_control_tools"):
            # Tool 1: pandapower network model to ePHASORSIM network model converter
            with dpg.tab(label="Converter: pandapower-to-ePHASORSIM"):
                dpg.add_text("Tool: PPtoePHASORSIM - pandapower network model to ePHASORSIM network model converter")
                dpg.bind_item_font(dpg.last_item(),TOOL_FONT)
                with dpg.group(horizontal=True, width=0):
                    input_name = "text_pickle_file"
                    dpg.add_button(label="Select network model (*.p):", callback=call_file_dialog, user_data=[1,input_name])
                    dpg.add_input_text(tag=input_name, hint="Path to *.p file",width=-1)
                with dpg.group(horizontal=True, width=0):
                    dpg.add_button(label="Run: load and convert network model", callback=load_pp_net_converter)
                    dpg.bind_item_theme(dpg.last_item(), "theme_execute")
                    dpg.add_loading_indicator(tag="loading_indicator", show=False)
                    dpg.add_text(tag="import_status", default_value="No network model has been loaded yet!", color=(255, 0, 0))

                # GUI for network model conversion
                pp_net_converter.create_gui()

        # Tool 2: CiLGenerator - ePHASORSIM Excel template to CiL Excel configuration
        with dpg.tab(label="Generator: CHIL Configuration", parent="tab_control_tools"):
            dpg.add_text("Tool: CiLGenerator - ePHASORSIM Excel template to CiL Excel configuration")
            dpg.bind_item_font(dpg.last_item(),TOOL_FONT)
            # Select the Excel template file
            with dpg.group(horizontal=True, width=0):
                input_name = "text_excel_template_file"
                dpg.add_button(label="Select ePHASORSIM model (*.xlsx):", callback=call_file_dialog, user_data=[0,input_name])
                dpg.add_input_text(tag=input_name, hint="Path to ePHASORSIM Excel template",width=-1)
            with dpg.group(horizontal=True, width=0):
                input_name = "pp_converted_net"
                dpg.add_button(label="Load pandapower network model (*.p):", callback=call_file_dialog, user_data=[1,input_name])
                dpg.add_input_text(tag=input_name, hint="Path to converted/compatible pandapower network model (*.p)",width=-1)
            with dpg.group(horizontal=True, width=0):
                dpg.add_button(label="Load ePHASORSIM Excel template and pandapower network model", callback=load_cil_generator)
                dpg.bind_item_theme(dpg.last_item(), "theme_execute")
                dpg.add_loading_indicator(tag="loading_indicator2", show=False)
                dpg.add_text(tag="import_status2", default_value="No ePHASORSIM model or pandapower network model has been loaded yet!", color=(255, 0, 0))

            # GUI for CHIL generator
            chil_generator.create_gui()

        # Separator for logging
        dpg.add_separator()
        dpg.add_separator()

#--------------------------------------------------------------------------------------------------------
# Generate the window / GUI when the script is started
if __name__ == "__main__":
    # Initialize objects 
    pp_net_converter = nmc.NetConverter()
    chil_generator = cgen.CiLGenerator()
    
    # Standard methods that define the "background window"
    dpg.create_context()    
    dpg.create_viewport(title=WINDOW_TITLE, small_icon=WINDOW_ICON, large_icon=WINDOW_ICON)
    dpg.setup_dearpygui()   
    
    create_gui() # Creates all widgets in the window
    
    # Define the viewport within the main window
    dpg.show_viewport()
    dpg.set_primary_window("win1", True)
    dpg.start_dearpygui()    # Starts the render loop
    dpg.destroy_context()    # Destroys the DearPyGui context