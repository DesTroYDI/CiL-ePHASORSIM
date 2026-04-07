# -*- coding: utf-8 -*-
"""
Dashboard.py
================
Visualization class for the CiL test bench (Controller-in-the-Loop).

Separates the GUI logic from the communication layer and uses a configured
``Controller`` as the data source.

@author: Groß, Hendrik
"""
import time, threading, json, platform

# DPG and CHIL imports
import pandas as pd
from collections import deque
import pandapower as pp
import dearpygui.dearpygui as dpg
from ..map import widget as dpg_map
from .Alert import Alert
from .AlertEvent import AlertEvent
from .MapOverlay import MapOverlayRenderer
from ..Enum import ReadMode
from ..Controller import Controller

class Dashboard:
    # --------------------------------------------------------------------------------------------------------
    # Percentage values for the panel sizes to be defined
    PERCENT_WIDTH_MAP: float = 0.58       # What percentage of the total width should the map occupy?
    PERCENT_HEIGHT_ALERTS: float = 0.25    # What percentage of the height should the message panel occupy?

    # --------------------------------------------------------------------------------------------------------
    # Color constants (RGBA int tuples 0-255)
    _COL_GREEN      = ( 29, 158, 117, 255)   # Normal state
    _COL_YELLOW     = (186, 117,  23, 255)   # Warning
    _COL_RED        = (163,  45,  45, 255)   # Limit violation
    _COL_TEXT_DIM   = (160, 160, 160, 255)   # Dimmed label text

    # --------------------------------------------------------------------------------------------------------
    # Additional visualization constants
    WINDOW_TITLE = "Controller Hardware-in-the-Loop (C-HiL) - Dashboard" # Window title
    WINDOW_ICON = ".\\Ressources\\iconH.ico"                                            # Window icon

    MAP_OPACITY: float = 0.6            # Transparency of map tiles
    MAX_DATAPOINTS: int = 500           # Maximum number of stored points
    TIME_VIEW: float = 10.0             # Visible time window in seconds (fixed) - Important: at least one network element must be visualized over time!
    
    # Cycle-time color coding
    QT_GOOD_MS: float = 750     # below -> green
    QT_WARN_MS: float = 2000    # below -> yellow, above -> red

    # --------------------------------------------------------------------------------------------------------
    # Constructor
    def __init__(self, _controller: Controller, _alert_list: list[Alert] | None = None, _vis_element_ignore: list[type] | None = None):
        """
        Initializes the dashboard with a controller, alert rules, and GUI filter.

        :param _controller: Connected and configured controller
        :type _controller: Controller
        :param _alert_list: List of alert conditions
        :type _alert_list: list[Alert]
        :param _vis_element_ignore: List of element classes to ignore in the visualization
        :type _vis_element_ignore: list[type]
        """
        # Controller object from the CiL implementation
        self.controller = _controller

        # Validate and store alert configurations
        if _alert_list is None:
            _alert_list = []
        self._alert_list: list[Alert] = _alert_list

        # Determine object classes that should not receive time-series visualization
        if _vis_element_ignore is None:
            _vis_element_ignore = []
        self.vis_element_ignore = _vis_element_ignore

        # Runtime control
        self._running: bool = False
        self._thread: threading.Thread | None = None
        self._start_time: float = 0.0           # perf_counter start time
        self._vis_start_time: float = 0.0       # time() start time

        # Energy values
        self._last_energy_time: float | None = None    
        self._energy_load_mwh: float = 0.0
        self._energy_gen_mwh: float = 0.0

        # DPG tags: performance statistics
        self._tag_sim_time: int | str = ""
        self._tag_query_ms: int | str = ""
        self._tag_se_ms: int | str = ""
        self._tag_gui_ms: int | str = ""

        # DPG tags: accumulated network load values
        self._tag_load_mw: int | str = ""
        self._tag_gen_mw: int | str = ""
        self._tag_load_mwh: int | str = ""
        self._tag_gen_mwh: int | str = ""

        # Time-series data for the timeline visualization
        self.uuid_x: int | str = ""
        self.uuid_y: int | str = ""
        self.uuid_data_bilanz: int | str = ""
        self.uuid_data_gen: int | str = ""
        self.uuid_data_load: int | str = ""
        # Data buffers for the timeline visualization
        self.data_time: deque[float] = deque(maxlen=self.MAX_DATAPOINTS)
        self.data_bilanz: deque[float] = deque(maxlen=self.MAX_DATAPOINTS)
        self.data_gen: deque[float] = deque(maxlen=self.MAX_DATAPOINTS)
        self.data_load: deque[float] = deque(maxlen=self.MAX_DATAPOINTS)

        # DPG tags: resizable containers
        self._tag_map_drawlist: int | str = ""
        self._tag_map_legend: int | str = ""
        self._tag_meld_child: int | str = ""
        self._tag_netzkarte: int | str = ""
        self._tag_netzkarte_title: int | str = ""
        self._tag_panel_alerts: int | str = ""
        self._map_overlay: MapOverlayRenderer | None  = None

        # Event log
        self._event_log: list[AlertEvent] = []
        self._alert_count: int = 0          # Number of event notifications
        # DPG tags: message panel
        self._tag_alert_count: int | str = ""    # Counter in the panel header
        self._tag_alert_nodata: int | str = ""   # Placeholder text (no configuration)

    # --------------------------------------------------------------------------------------------------------
    # Public/Internal methods
    def start(self, dpg_parent: int | None = None, try_connect: int = 5, sleep: int = 2) -> bool:
        """
        Starts the dashboard including connection checks, GUI setup, and render loop.

        :param dpg_parent: Optional DPG tag of an existing window.
                           If None is passed, start() creates its own
                           viewport and primary window.
        :type dpg_parent: int | None
        :param try_connect: Number of connection attempts before aborting
        :type try_connect: int
        :param sleep: Wait time in seconds between connection attempts
        :type sleep: int
        :return: ``True`` on successful start, otherwise ``False``
        :rtype: bool
        """
        # Check PandaPower network model
        pp_net = self.controller.pp_net
        if pp_net is None:
            print("PP_NET_NONE - No PandaPower network model available. Aborting!")
            return False
        if "geo" not in pp_net.bus.columns:
            print("PP_NET_MISSING_COORDINATES - No geographic coordinates ('geo') in the network model. Aborting!")
            return False
        if pp_net.bus['geo'].isna().all().all():
            print("PP_NET_COORDINATES_NONE - Geographic coordinates are empty. Aborting!")
            return False
        print("PP_NET_SUCCESS - PandaPower network model with coordinates found successfully.")

        # ── Establish Modbus connection ─────────────────────────────────────────────────────
        for idx in range(try_connect):
            print(f"  DASHBOARD - Connection test [{idx + 1}|{try_connect}]...")
            if self.controller.test_modbus():
                break
            time.sleep(sleep)
        else:
            print("DASHBAORD_CONNNECTION_SUCCESS - Connection failed. Aborting!")
            return False

        self.controller.connect()

        # ── Build GUI ─────────────────────────────────────────────────────
        try:
            if dpg_parent is None:
                dpg.create_context()
                dpg.create_viewport(title=self.WINDOW_TITLE, small_icon=self.WINDOW_ICON, large_icon=self.WINDOW_ICON)
                dpg.setup_dearpygui()
                dpg.maximize_viewport()
                dpg.show_viewport()

                win_tag = dpg.generate_uuid()
                with dpg.window(label=self.WINDOW_TITLE, tag=win_tag):
                    dpg.set_primary_window(win_tag, True)
                    self._build(win_tag)
                
                # Automatically adjust the window scaling
                dpg.set_viewport_resize_callback(self._on_viewport_resize)
            else:
                if not dpg.is_dearpygui_running():
                    raise RuntimeError(f"DPG_NOT_RUNNING - dpg_parent={dpg_parent} was provided, but DearPyGui is not running.")
                if not dpg.does_item_exist(dpg_parent):
                    raise RuntimeError(f"DPG_PARENT_NONEXISTING - tag {dpg_parent} was not found.")
                self._build(dpg_parent)
        except Exception as exc:
            print(f"LEISTAND_GUI_FAILED - GUI build failed: {exc}")
            return False

        # ── Start update thread ────────────────────────────────────────────
        self._running = True
        self._thread = threading.Thread(target=self._update_loop, daemon=True)
        self._thread.start()

        # ── DearPyGui render loop (blocking) ────────────────────────────────
        dpg.set_frame_callback(30, self._on_viewport_resize)        # Run scaling once after startup for correct display
        dpg.set_frame_callback(60, self._on_zoom_to_network_btn)    # Zoom to the network model once at startup
        dpg.start_dearpygui()

        # ── Cleanup after window close ────────────────────────────────
        self.stop()
        return True

    def stop(self) -> bool:
        """
        Stops the update thread and disconnects the Modbus connection.

        :return: Always ``True``
        :rtype: bool
        """
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
        self.controller.disconnect()
        return True
    
    def _on_zoom_to_network_btn(self, sender, app_data, user_data):
        """Callback to zoom the map to the full network extent."""
        if self._map_overlay is None or not self._map_overlay.zoom_to_network():
            print("DASHBOARD_ZOOM_NETWORK_FAILED - No valid geographic coordinates found for zoom-to-fit.")

    def __filter_line_series_data(self, data_queue: deque[float]) -> tuple[list[float],list[float]]:
        """
        Filters time-series data to the currently visible time window.
        
        :param data_queue: Data queue with Y values (deque)
        :type data_queue: deque[float]
        :return: Visible X and Y values as a synchronized tuple
        :rtype: tuple[list[float],list[float]]
        """
        if not self.data_time or not data_queue:
            return [], []
    
        x_max = self.data_time[0]
        x_min = max(0.0, x_max - (self.TIME_VIEW*2))

        # Plot only points within the visible window
        t_all = list(self.data_time)
        visible_idx = [i for i, v in enumerate(t_all) if x_min <= v <= x_max]

        # Relevant time values (X axis) and data values (data list)
        x_visible = [t_all[i] for i in visible_idx]
        y_visible = [list(data_queue)[i] for i in visible_idx]

        # Return the X and Y values for the configured display window
        return x_visible, y_visible

    # --------------------------------------------------------------------------------------------------------
    # GUI setup
    def _on_viewport_resize(self, sender, app_data):
        """
        Callback for viewport size changes.

        Recalculates panel dimensions and adjusts the map and alert areas.
        """
        # Width and height of the entire viewport
        vp_w     = dpg.get_viewport_width()
        vp_h     = dpg.get_viewport_height()
        
        LEFT_W   = int(vp_w * self.PERCENT_WIDTH_MAP)       # Map width
        MELD_H = int(vp_h * self.PERCENT_HEIGHT_ALERTS)     # Message panel height

        # Rescale the panel based on the viewport width and height
        try:
            # Set the message panel height
            dpg.configure_item(self._tag_panel_alerts, height=MELD_H)

            # Set the map width and resize the map
            # Compute the height excluding the title
            title_height = dpg.get_item_rect_size(self._tag_netzkarte_title)[1]
            map_height = (vp_h-title_height)  - 75 
            dpg.configure_item(self._tag_netzkarte, width=LEFT_W)
            self._map_widget.resize(LEFT_W, map_height)          
        except Exception as exc:
            print(f"LEITSTAND_RESIZE_ERROR - {exc}")

    def _build(self, dpg_parent: int | str):
        """
        Builds the complete dashboard GUI inside the given parent.

        :param dpg_parent: DPG tag of the parent window
        :type dpg_parent: int | str
        """
        self._start_time = time.perf_counter()
        self._vis_start_time = time.time()

        # ── Dark dashboard theme ──────────────────────────────────────────
        with dpg.theme() as _theme:
            with dpg.theme_component(dpg.mvAll):
                # Background
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (18, 18, 18))
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (30, 30, 30))

                # Default text color
                dpg.add_theme_color(dpg.mvThemeCol_Text, (220, 220, 220))

                # Accent (blue)
                dpg.add_theme_color(dpg.mvThemeCol_Button, (45, 90, 160))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (65, 120, 200))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (35, 70, 140))

                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (40, 40, 50, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Header, (45, 45, 60, 255))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (55, 55, 75, 255))
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 6, 4)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 4)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 8)
        dpg.bind_item_theme(dpg_parent, _theme)

        # ── Define fonts and sizes ──────────────────────────────────────────
        with dpg.font_registry():
            if platform.system() == "Windows":
                # Windows font paths
                _regular_font = "C:/Windows/Fonts/segoeui.ttf"
                _title_font   = "C:/Windows/Fonts/segoeuib.ttf"
                _small_font   = "C:/Windows/Fonts/segoeui.ttf"
            else:
                # Linux font paths
                _regular_font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
                _title_font   = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                _small_font   = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            # Create DPG fonts
            self.regular_font = dpg.add_font(_regular_font, 18)
            self.title_font = dpg.add_font(_title_font, 26)
            self.small_font = dpg.add_font(_small_font, 15)
        
        # Configure the panel layout
        with dpg.group(parent=dpg_parent,horizontal=True):
            self._build_panel_netzkarte()
            with dpg.group():
                self._build_status_topbar()
                with dpg.child_window(border=False, auto_resize_y=True):
                    with dpg.group(horizontal=True):
                        self._build_panel_sums()
                        self._build_panel_sums_timeline()
                self._build_panel_alerts()
                dpg.add_separator()
                self._build_panel_timelines()

    def _build_status_topbar(self):
        """Creates the top bar with connection and performance indicators."""
        with dpg.child_window(auto_resize_y=True):
            # Heading with the simulation time
            with dpg.group(horizontal=True):
                dpg.add_text("Simulation time:")
                dpg.bind_item_font(dpg.last_item(), self.title_font)
                self._tag_sim_time = dpg.add_text("00:00:00")
                dpg.bind_item_font(self._tag_sim_time, self.title_font)
            dpg.add_separator()

            with dpg.group(horizontal=True):
                # Display query time to the host
                dpg.add_text(f"Host= {self.controller.host} : {self.controller.port}    Cycle time:")
                dpg.bind_item_font(dpg.last_item(), self.regular_font)
                self._tag_query_ms = dpg.add_text("--- ms",color=self._COL_GREEN)
                dpg.bind_item_font(self._tag_query_ms, self.regular_font)

                # State estimation
                dpg.add_text("     SE-Time:")
                dpg.bind_item_font(dpg.last_item(), self.regular_font)
                self._tag_se_ms = dpg.add_text("--- ms")
                dpg.bind_item_font(self._tag_se_ms, self.regular_font)

                # GUI update
                dpg.add_text("     GUI-Update:")
                dpg.bind_item_font(dpg.last_item(), self.regular_font)
                self._tag_gui_ms = dpg.add_text("--- ms")
                dpg.bind_item_font(self._tag_gui_ms, self.regular_font)

    def _build_panel_netzkarte(self):
        """Creates the panel with an interactive network map and hover information."""
        self._tag_netzkarte = dpg.generate_uuid()
        self._tag_netzkarte_title = dpg.generate_uuid()
        with dpg.child_window(border=True, tag=self._tag_netzkarte, auto_resize_y=True):
            with dpg.child_window(border=False, auto_resize_y=True, tag=self._tag_netzkarte_title):
                dpg.add_text("Map")
                dpg.bind_item_font(dpg.last_item(), self.title_font)
                dpg.add_separator()

                # Determine the central coordinates from the PandaPower network model
                geo = self.controller.pp_net.bus.at[0, "geo"] # pyright: ignore[reportOptionalMemberAccess]
                point = json.loads(geo)
                lon, lat = point["coordinates"]

                with dpg.group(horizontal=True):
                    # Button to zoom to the full network extent
                    _tag_map_zoom = dpg.add_button(label="Zoom to Network", callback=self._on_zoom_to_network_btn)
                    dpg.bind_item_font(_tag_map_zoom, self.regular_font)
                    # Text elements that show information on hover
                    _tag_map_hover_info = dpg.add_text("Info: ")
                    dpg.bind_item_font(_tag_map_hover_info, self.regular_font)
                    _tag_map_hover_info = dpg.add_text("-")
                    dpg.bind_item_font(_tag_map_hover_info, self.regular_font)

            # Add the map with OSM tiles
            self._map_widget, self._tag_map_drawlist = dpg_map.add_map_widget(
                width=100,
                height=100,
                center=(lat,lon),
                zoom_level=12,
                tile_opacity=self.MAP_OPACITY)

            # Define/configure the UI layer for the PandaPower network model
            self._map_overlay = MapOverlayRenderer(
                pp_net=self.controller.pp_net, # pyright: ignore[reportArgumentType]
                map_widget=self._map_widget,
                map_drawlist_tag=self._tag_map_drawlist, # pyright: ignore[reportArgumentType]
                hover_text_tag=_tag_map_hover_info, # pyright: ignore[reportArgumentType]
            )
            # Build the map layer for the PandaPower network model and zoom to it
            self._map_overlay.build_overlay()

    def _build_panel_sums(self):
        """Creates the panel with aggregated power and energy values."""
        # Calculate the row height from the font size so the table always has enough space
        _row_h = int(dpg.get_item_configuration(self.regular_font)["size"] * 2.5)

        with dpg.child_window(border=True, auto_resize_x=True, auto_resize_y=True):
            dpg.add_text("Grid Information")
            dpg.bind_item_font(dpg.last_item(), self.title_font)
            dpg.add_separator()
            # Table with summed network information
            with dpg.table(header_row=False,borders_innerV=False, borders_outerV=False,policy=dpg.mvTable_SizingFixedFit):
                # Add three columns (name, value, unit)
                for _ in range(3):
                    dpg.add_table_column()

                # Create data rows
                with dpg.table_row(height=_row_h):
                    tmp1 = dpg.add_text("Total load")
                    self._tag_load_mw  = dpg.add_text("--.-")
                    tmp2 = dpg.add_text("MW")
                    dpg.bind_item_font(tmp1, self.regular_font)
                    dpg.bind_item_font(self._tag_load_mw, self.regular_font)
                    dpg.bind_item_font(tmp2, self.regular_font)

                with dpg.table_row(height=_row_h):
                    tmp1 = dpg.add_text("Total feed-in")
                    self._tag_gen_mw  = dpg.add_text("--.-")
                    tmp2 = dpg.add_text("MW")
                    dpg.bind_item_font(tmp1, self.regular_font)
                    dpg.bind_item_font(self._tag_gen_mw, self.regular_font)
                    dpg.bind_item_font(tmp2, self.regular_font)
                
                # Empty row as spacer
                with dpg.table_row():
                    dpg.add_separator()
                    dpg.add_separator()
                    dpg.add_separator()

                with dpg.table_row(height=_row_h):
                    tmp1 = dpg.add_text("Total energy consumption")
                    self._tag_load_mwh  = dpg.add_text("--.-")
                    tmp2 = dpg.add_text("MWh")
                    dpg.bind_item_font(tmp1, self.regular_font)
                    dpg.bind_item_font(self._tag_load_mwh, self.regular_font)
                    dpg.bind_item_font(tmp2, self.regular_font)

                with dpg.table_row(height=_row_h):
                    tmp1 = dpg.add_text("Total feed-in energy")
                    self._tag_gen_mwh  = dpg.add_text("--.-")
                    tmp2 = dpg.add_text("MWh")
                    dpg.bind_item_font(tmp1, self.regular_font)
                    dpg.bind_item_font(self._tag_gen_mwh, self.regular_font)
                    dpg.bind_item_font(tmp2, self.regular_font)

    def _build_panel_sums_timeline(self):
        """Creates the time series of aggregated network totals."""
        _uuid = dpg.generate_uuid()
        self.uuid_x = f"net_x_axis_{_uuid}"
        self.uuid_y = f"net_y_axis_{_uuid}"
        self.uuid_data_bilanz = f"y_axis_bilanz_{_uuid}"
        self.uuid_data_gen = f"y_axis_gen_{_uuid}"
        self.uuid_data_load = f"y_axis_load_{_uuid}"

        # Propagate the dashboard TIME_VIEW to all controller elements
        for element in self.controller.component_list:
            element.TIME_VIEW = self.TIME_VIEW

        with dpg.child_window(border=True, autosize_y=True, width=-1,height=-1):
            with dpg.plot(no_title=True, no_inputs=True, width=-1,height=-1):
                dpg.add_plot_legend(location=dpg.mvPlot_Location_NorthEast)
                # X axis
                dpg.add_plot_axis(dpg.mvXAxis, tag=self.uuid_x)
                dpg.set_axis_limits(self.uuid_x, 0.0, self.TIME_VIEW)

                # Y axis
                with dpg.plot_axis(dpg.mvYAxis, tag=self.uuid_y):
                    dpg.add_line_series([], [], label="Power balance", tag=self.uuid_data_bilanz)
                    dpg.add_line_series([], [], label="Feed-in power", tag=self.uuid_data_gen)
                    dpg.add_line_series([], [], label="Drawn power", tag=self.uuid_data_load)
                dpg.set_axis_limits_auto(self.uuid_y)

    def _build_panel_alerts(self):
        """
        Creates the persistent event log in the message panel.

        The panel shows every occurring ``AlertEvent`` as a permanent row.
        New events are inserted at the top (newest first).
        Older entries remain visible permanently.

        If no configurations were passed, a hint text is shown.
        """
        self._tag_panel_alerts = dpg.generate_uuid()
        with dpg.child_window(border=True, tag=self._tag_panel_alerts):
            dpg.add_text("Alerts")
            dpg.bind_item_font(dpg.last_item(), self.title_font)
            # Header with event counter
            with dpg.group(horizontal=True):
                self._tag_alert_count = dpg.add_text(f"Alerts - 0 events [{len(self._alert_list)} conditions configured]", color=self._COL_TEXT_DIM)

                dpg.bind_item_font(self._tag_alert_count, self.small_font)
            dpg.add_separator()
            # Scrollable log area
            self._tag_meld_child = dpg.add_child_window(border=False)
            if not self._alert_list:
                # Hint: no conditions configured
                with dpg.group(parent=self._tag_meld_child):
                    self._tag_alert_nodata = dpg.add_text(
                        "No alert configuration was provided. Create an _alert_list=[VoltageBandAlert(...), ... ] when instantiating the dashboard.",
                        color=self._COL_TEXT_DIM, wrap=0)

    def _build_panel_timelines(self):
        """Creates time-series tabs for all non-ignored network elements."""
        with dpg.child_window(border=True, height=-1, width=-1):
            dpg.add_text("Time Series")
            dpg.bind_item_font(dpg.last_item(), self.title_font)
            dpg.add_separator()

            # Store tab information for the combo box
            tab_labels = []
            tab_uuids = []

            # Add all network element time series
            uuid_combo = dpg.add_combo(width=-1,callback=lambda s, a, u: (
                [dpg.hide_item(tab) for tab in u["tabs"]],
                dpg.show_item(u["tabs"][u["labels"].index(a)])
            ),user_data={"tabs": tab_uuids, "labels": tab_labels})

            with dpg.tab_bar():
                for net_element in self.controller.component_list:
                    # Check whether the network element class is in the ignore list
                    if type(net_element) not in self.vis_element_ignore:
                        
                        # Create a tab with visualization
                        tab_uuid = dpg.generate_uuid()
                        tab_label = f"{net_element.__class__.__name__} - '{net_element.name}'"

                        # ComboBox-Werte
                        tab_uuids.append(tab_uuid)
                        tab_labels.append(tab_label)

                        with dpg.tab(tag=tab_uuid, label=tab_label):
                            net_element.start_visualize(tab_uuid)
                        # Hide this initially due to the large number of possible network elements
                        if len(tab_labels) > 1:
                            dpg.hide_item(tab_uuid)
            
            # Set values in the combo box
            dpg.configure_item(uuid_combo,items=tab_labels)
            dpg.set_value(uuid_combo,tab_labels[0])
            dpg.bind_item_font(uuid_combo, self.regular_font)

    # --------------------------------------------------------------------------------------------------------
    # Update-Loop (Hintergrund-Thread)
    def _update_loop(self):
        """Background thread for cyclic data polling and GUI updates."""
        while self._running:

            # ── Measure query time ────────────────────────────────────────
            # Read all ePHASORSIM Modbus values and treat them as measurements
            _t0 = time.perf_counter()
            self.controller.read_all(ReadMode.MODBUS)
            query_ms = (time.perf_counter() - _t0) * 1000.0
            
            # Build measurements for state estimation
            _t0 = time.perf_counter()
            self._build_se_measurements()
            se_ms = 0
            # Perform state estimation and read PandaPower values after state estimation
            try:
                _t_se = time.perf_counter()
                est_result = pp.estimation.estimate( # pyright: ignore[reportAttributeAccessIssue]
                    net=self.controller.pp_net, init="results", algorithm="wls",
                    maximum_iterations=10)
                se_ms = (time.perf_counter() - _t_se) * 1000.0
                
                # Transfer result values for loads and generators from the results back into master data
                if est_result["success"]:
                    self.controller.pp_net.sgen.loc[self.controller.pp_net.res_sgen.index, "p_mw"] = self.controller.pp_net.res_sgen["p_mw"].values # pyright: ignore[reportOptionalMemberAccess]
                    self.controller.pp_net.sgen.loc[self.controller.pp_net.res_sgen.index, "q_mvar"] = self.controller.pp_net.res_sgen["q_mvar"].values # pyright: ignore[reportOptionalMemberAccess]
                else:
                    raise RuntimeError("State estimation failed")
                # Read the resulting PandaPower values after state estimation
                self.controller.read_all(ReadMode.PANDAPOWER)
            except Exception as e:
                print(f"SE_FAILED - State estimation failed: {e}")
            se_full_ms = (time.perf_counter() - _t0) * 1000.0

            # ── Simulation time and polling cycles ───────────────────────────────────────────────
            _t0 = time.perf_counter()

            sim_s  = _t0 - self._start_time
            sim_str = "{:02d}:{:02d}:{:02d}".format(int(sim_s // 3600), int((sim_s % 3600) // 60), int(sim_s % 60))
            
            # ── Evaluate alert conditions ──────────────────────────────
            self._evaluate_alerts()

            # ── Update DPG widgets ────────────────────────────────
            if not dpg.is_dearpygui_running():
                break
            try:
                # ── Fetch total power values from the PandaPower network model (state estimation) ──────────────────────────────
                _total_load_mw = self.controller.pp_net.res_load["p_mw"].sum() # pyright: ignore[reportOptionalMemberAccess]
                _total_gen_mw  = self.controller.pp_net.res_sgen["p_mw"].sum() # pyright: ignore[reportOptionalMemberAccess]

                # Set values in the GUI and add them to the timeline
                dpg.set_value(self._tag_load_mw,f"{_total_load_mw:.3f}")
                dpg.set_value(self._tag_gen_mw,f"{_total_gen_mw:.3f}")

                time_relative = (time.time() - self._vis_start_time)
                self.data_time.appendleft(time_relative)
                self.data_gen.appendleft(-_total_gen_mw)
                self.data_load.appendleft(_total_load_mw)
                self.data_bilanz.appendleft(_total_load_mw-_total_gen_mw)

                # Filter the data display - use time data from the first element
                x_visible, gen_visible = self.__filter_line_series_data(self.data_gen)
                x_visible, load_visible = self.__filter_line_series_data(self.data_load)
                x_visible, bilanz_visible = self.__filter_line_series_data(self.data_bilanz)
                
                # Update the visualization (DPG can also do this from the subthread)
                dpg.set_value(self.uuid_data_gen, [x_visible, gen_visible])
                dpg.set_value(self.uuid_data_load, [x_visible, load_visible])
                dpg.set_value(self.uuid_data_bilanz, [x_visible, bilanz_visible])

                # X axis: newest value on the right, window scrolls to the right
                x_max = time_relative
                x_min = max(0.0, time_relative - self.TIME_VIEW)    # Padding so twice as many values are shown as the display window contains 
                dpg.set_axis_limits(self.uuid_x, x_min, x_max)               

                # Automatically adjust the Y-axis scaling so all visible values stay within the window
                all_visible = bilanz_visible + gen_visible + load_visible
                y_min = min(all_visible)
                y_max = max(all_visible)
                padding = (y_max - y_min) * 0.1 or 0.1
                dpg.set_axis_limits(self.uuid_y, y_min - padding, y_max + padding)

                # ── Energy integration (trapezoidal rule) ──────────────────────────
                if self._last_energy_time is not None:
                    dt_h = (time_relative - self._last_energy_time) / 3600.0    # Seconds -> hours
                    self._energy_load_mwh += _total_load_mw * dt_h
                    self._energy_gen_mwh  += _total_gen_mw  * dt_h
                self._last_energy_time = time_relative

                dpg.set_value(self._tag_load_mwh, f"{self._energy_load_mwh:.3f}")
                dpg.set_value(self._tag_gen_mwh,  f"{self._energy_gen_mwh:.3f}")

                # Statistics display ──────────────────────────────
                dpg.set_value(self._tag_sim_time, sim_str)

                query_time_color = (self._COL_GREEN
                          if query_ms < self.QT_GOOD_MS
                          else self._COL_YELLOW
                          if query_ms < self.QT_WARN_MS
                          else self._COL_RED)
                dpg.set_value(self._tag_query_ms, f"{query_ms:6.1f} ms")
                dpg.configure_item(self._tag_query_ms, color=query_time_color)

                # Duration of the pure state estimation
                se_ms_txt = f"wls={se_ms:6.1f} ms" if se_ms > 0 else "-- ms"    
                # Color depending on whether the state estimation was successful or not
                se_color = (self._COL_GREEN if est_result["success"] else self._COL_RED)    # pyright: ignore[reportPossiblyUnboundVariable]
                dpg.set_value(self._tag_se_ms, f"{se_full_ms:6.1f} ms [{se_ms_txt}]")
                dpg.configure_item(self._tag_se_ms, color=se_color)

                # GUI update duration
                gui_ms = (time.perf_counter() - _t0) * 1000.0
                dpg.set_value(self._tag_gui_ms, f"{gui_ms:6.1f} ms")
            except Exception as e:
                print(f"LEITSTAND_GUI_UPDATE_ERROR - Error during GUI update: {e}")

    def _evaluate_alerts(self):
        """
        Evaluates all configured alert conditions.

        On a positive edge, ``alert.check_and_update()`` returns a new ``AlertEvent`` that is added to ``_event_log`` in a thread-safe way.
        New events are immediately added as DPG rows in the message area.
        """
        new_events: list[AlertEvent] = []

        # Check all conditions
        for alert in self._alert_list:
            try:
                event = alert.check_and_update()
                # A new event has occurred
                if event is not None:
                    new_events.append(event)
            except Exception as exc:
                print(f"ALERT_EVAL_ERROR - [{alert.label}]: {exc}")

        # If a new message event occurred, create it
        if new_events:
            # Determine the first row of the message window
            first_event = None
            try:
                _events = dpg.get_item_children(self._tag_meld_child, slot=1)
                if _events:
                    first_event = _events[0]
            except Exception:
                pass
            
            # Update event count
            self._alert_count += len(new_events)
            dpg.set_value(self._tag_alert_count, f"Alerts - {self._alert_count} events [{len(self._alert_list)} conditions configured]")

            # Create all alerts
            for event in new_events:
                # Create DPG message row
                first_event = event.build_dpg_row(
                    _start_timestamp= self._vis_start_time,
                    parent_tag=self._tag_meld_child, # pyright: ignore[reportArgumentType]
                    before_tag=first_event, # pyright: ignore[reportArgumentType]
                )

                # Format DPG message row
                for child in dpg.get_item_children(first_event,1): # pyright: ignore[reportOptionalIterable]
                    if dpg.get_item_type(child) == "mvAppItemType::mvText":
                        dpg.bind_item_font(child, self.regular_font)

    def _build_se_measurements(self):
        """
        Transfers the current Modbus values into the pandapower network model as measurements.

        For performance, a manual DataFrame insert is used to prepare the
        subsequent state estimation.

        Supported measurements:
            Bus     -> vm_pu (voltage magnitude), va_degree (voltage angle)
            Load    -> p_mw, q_mvar  (as 'p' / 'q' at the bus)
            Generator (sgen) -> p_mw, q_mvar

        .. note::
        The direct DataFrame insert (manual=True) bypasses pp.create_measurement() and avoids O(n^2) behavior for large component counts.
        """
        # Delete all measurements in the network model
        self.controller.pp_net.measurement.drop(self.controller.pp_net.measurement.index, inplace=True) # pyright: ignore[reportOptionalMemberAccess]

        # Collect measurement values from the Modbus values
        measurements = []
        for element in self.controller.component_list:
            measurements += element.create_pp_measurements(True)

        # Create all measurements manually in a DataFrame (for performance reasons)
        if measurements:
            df_measurements = pd.DataFrame(measurements)
            self.controller.pp_net.measurement = pd.concat( [self.controller.pp_net.measurement, df_measurements], ignore_index=True) # pyright: ignore[reportOptionalMemberAccess]
