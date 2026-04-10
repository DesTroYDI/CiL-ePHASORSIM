# -*- coding: utf-8 -*-
"""
IModbusElement.py
@author: Groß, Hendrik
"""
import uuid, time, asyncio
import dearpygui.dearpygui as dpg
from collections import deque
from openpyxl import Workbook 
import pandapower as pp
from abc import ABC, abstractmethod
from pymodbus.client import AsyncModbusTcpClient

# Import base classes
from .Value import ModbusValue, PandaPowerValue
from .Enum import ModbusDataType, DataType, ReadMode

class IModbusElement(ABC):
    """
    Abstract base class for all Modbus-capable network components.

    The class bundles common functionality for:
    - Managing ``ModbusValue`` and ``PandaPowerValue`` entries
    - Asynchronous reading/writing
    - Excel import/export of the configuration
    - Standardized real-time visualization
    """
    pp_net: pp.pandapowerNet        
    df_pp: str                          # Information: DataFrame in pandapower that contains the element (e.g. "bus", "line", "load", etc.)

    # Data storage and visualization configuration
    VIS_INIT: bool = False              # Flag that an object can override to determine whether a visualization was initialized
    MAX_DATAPOINTS: int = 500           # Maximum stored points
    TIME_VIEW: float = 10.0             # Visible time window in seconds (fixed)

    # Required dictionary keys (created as PandaPowerValue if missing)
    LIST_VALUE_KEYS: list[str] = []
    # Dictionary for measurement assignment (defines which keys can be used as measurement values and what type they are)
    DICT_MEASUREMENT: dict[str,str]= {}

    # Constructor
    def __init__(self, _name: str, _net_index: int, _values: dict[str, ModbusValue | PandaPowerValue] = {}):
        """
        Initializes a network component with a name, network index, and value container.

        :param _name: Unique component name
        :type _name: str
        :param _net_index: Index in the pandapower DataFrame
        :type _net_index: int
        :param _values: Dictionary of register definitions
        :type _values: dict[str, ModbusValue | PandaPowerValue]
        :raises TypeError: If _values is not a dictionary
        """
        # PandaPower information          
        self.name: str = _name                   # Name used to identify the object in the network model
        self.net_index: int = _net_index         # Identifier of the object in the network model (the object can be addressed through this index)
            
        # Check whether values were passed as a dictionary
        if not isinstance(_values, dict):
            raise TypeError("Internal values were not provided as a dictionary!")
        self.values: dict[str, ModbusValue | PandaPowerValue] = _values             # Dictionary of ModbusValues/PandaPowerValue that a component can have

        # Asynchronous Modbus communication
        self.event_loop: asyncio.AbstractEventLoop          # Persistent event loop for all async operations
        self.modbus_client: AsyncModbusTcpClient | None     # Modbus master (TCP/IP client)

        # UUIDs of the DPG visualization controls
        self.uuid_vis_parent:int | str | None = None
        self.uuid_x:int | str | None = None
        self.uuid_y:int | str | None = None
        self.uuid_data:int | str | None = None
        self.uuid_text:int | str | None = None

    # --------------------------------------------------------------------------------------------------------
    # Attribute
    @property
    def controllable(self) -> bool:
        """
        Checks whether the component has at least one writable Modbus value.
        """
        for mv in self.values.values():
            # If there is a writable Modbus value, it is a controllable object
            if isinstance(mv, ModbusValue) and not mv.modbus_data_type.is_read_only:
                return True
        return False

    @property
    @abstractmethod
    def value(self) -> float:
        """Abstract attribute for the primary component value."""
        raise NotImplementedError("Absctract attribute not implemented!")

    @property
    @abstractmethod
    def unit(self) -> str:
        """Abstract attribute for the unit of the primary component value."""
        raise NotImplementedError("Absctract attribute not implemented!")

    # --------------------------------------------------------------------------------------------------------
    # Modbus methods
    def set_modbus_client(self, _modbus_client: AsyncModbusTcpClient | None):
        """
        Sets a shared Modbus client for the component and its Modbus values.

        :param _modbus_client: Connected Modbus TCP client or None
        :type _modbus_client: AsyncModbusTcpClient | None
        """
        self.modbus_client = _modbus_client
        for mv in self.values.values():
            if isinstance(mv, ModbusValue):
                mv.modbus_client = _modbus_client

    # --------------------------------------------------------------------------------------------------------
    # Communication methods
    def read(self, mode: ReadMode = ReadMode.ALL) -> dict[str, ModbusValue | PandaPowerValue]:
        """
        Performs a synchronous read via the event loop.

        :param mode: Data source (Modbus, pandapower, or both)
        :type mode: ReadMode
        :return: Updated values
        :rtype: dict[str, ModbusValue | PandaPowerValue]
        """
        return self.event_loop.run_until_complete(self.read_async(mode))

    async def read_async(self, mode: ReadMode = ReadMode.ALL) -> dict[str, ModbusValue | PandaPowerValue]:
        """
        Reads Modbus and/or pandapower values asynchronously.

        Missing required keys from ``LIST_VALUE_KEYS`` are added as ``PandaPowerValue``.
        Modbus values are read in parallel, pandapower values are read directly from
        DataFrames (``res_<df_pp>`` and ``<df_pp>``).

        :param mode: Data source (Modbus, pandapower, or both)
        :type mode: ReadMode
        :return: Updated values
        :rtype: dict[str, ModbusValue | PandaPowerValue]
        """
        # If required dictionary value keys are missing, add them as PandaPowerValue placeholders
        for _key in self.LIST_VALUE_KEYS:
            if not _key in self.values:
                self.values[_key] = PandaPowerValue()

        # Data validation
        mode = ReadMode(mode.value)
        # Split the items
        modbus_items = [(k, v) for k, v in self.values.items() if isinstance(v, ModbusValue) and mode in (ReadMode.MODBUS, ReadMode.ALL)]
        pp_items     = [(k, v) for k, v in self.values.items() if isinstance(v, PandaPowerValue) and mode in (ReadMode.PANDAPOWER, ReadMode.ALL)]

        # Read Modbus values in parallel (all registers of one element at once)
        async def _read_one(key: str, mv: ModbusValue):
            try:
                await mv.read()
            except Exception as e:
                print(f"Error reading Modbus-Value '{key}': {e}")
        # Read Modbus values in parallel
        if modbus_items and self.modbus_client is not None and self.modbus_client.connected:
            await asyncio.gather(*(_read_one(k, v) for k, v in modbus_items))

        # Read PandaPower values synchronously (no I/O, no await needed)
        for key, value in pp_items:
            key_found = False
            lst_sdf = [f"res_{self.df_pp}", self.df_pp]
            for _sdf in lst_sdf:
                if hasattr(self.pp_net, _sdf):
                    df = getattr(self.pp_net, _sdf)
                    if key in df.columns:
                        value.value = df.at[self.net_index, key]
                        key_found = True
                        break
            
            # Log if the key was not found
            if not key_found:
                print(f"DataFrame '{str(lst_sdf)}' of class '{self.__class__.__name__}' not '{key}' in pandapower grid model found!")
        return self.values

    def write(self, _values: dict[str, ModbusValue | PandaPowerValue] | None = None):
        """
        Writes values to Modbus and/or pandapower.

        If ``_values`` is not provided, all currently stored values are used.

        :param _values: Optional subset of values to write
        :type _values: dict[str, ModbusValue | PandaPowerValue] | None
        :return: Written values
        :rtype: dict[str, ModbusValue | PandaPowerValue]
        """
        # If no ModbusValues/PandaPowerValue are provided, use the ones from the component instance
        # Otherwise, only specific values can be passed and written
        if _values is None:
            _values = self.values

        for key,value in _values.items():
            # If it is a Modbus value, write it there
            if isinstance(value, ModbusValue):
                # Only write the value if it is also a writable register
                if not value.modbus_data_type.is_read_only:
                    self.event_loop.run_until_complete(value.write())
            # If it is a value from the PandaPower network model, write that value
            elif isinstance(value, PandaPowerValue):
                # Resolve the target pandapower DataFrame (for example: sgen)
                if hasattr(self.pp_net,self.df_pp):
                    df = getattr(self.pp_net,self.df_pp)
                    if key in df.columns:
                        df.at[self.net_index, key] = value.value
                        break
                    else:
                        print(f"Column '{key}' not found in DataFrame '{self.df_pp}'!")
                else:
                    print(f"DataFrame '{self.df_pp}' of class '{self.__class__.__name__}' could not be found in pandapower grid model!")
        return _values

    # --------------------------------------------------------------------------------------------------------
    # Configuration management / visualization
    def write_to_excel(self, _wb: Workbook):
        """
        Writes component and register configuration into a workbook.

        :param _wb: openpyxl.Workbook with prepared Sheets
        :type _wb: Workbook
        """
        # Generate UUID and determine class
        _uuid = str(uuid.uuid4())
        class_name = self.__class__.__name__

        # Write component information
        _wb["Components"].append([_uuid, class_name, self.name, self.net_index])
        
        # Write ModbusValues
        for k,mv in self.values.items():
            if isinstance(mv, ModbusValue):
                # Validate data types (import errors)
                mv.modbus_data_type = ModbusDataType(mv.modbus_data_type.value) 
                mv.data_type = DataType(mv.data_type.value)  

                modbus_data_type = mv.modbus_data_type.value  # Determine Modbus data type from enum
                data_type = mv.data_type.label  # Determine data type from enum
                _wb["ModbusValues"].append([_uuid,k,modbus_data_type,data_type,mv.address,mv.unit,mv.scale])

    def start_visualize(self, _parent: int|str):
        """
        Initializes the default real-time visualization of the component.

        Data buffers and the DearPyGui elements for text display and the line chart are created.

        :param _parent: Parent container in DearPyGui
        :type _parent: int | str
        """
        # Create data buffers
        self.data_time: deque[float] = deque(maxlen=self.MAX_DATAPOINTS)       # Data buffer for time values
        self.data_value: deque[float] = deque(maxlen=self.MAX_DATAPOINTS)      # Data buffer for the Y axis

        # Create UUIDs for visualization
        self.uuid_vis_parent = _parent
        _uuid = dpg.generate_uuid()
        self.uuid_x = f"x_axis_{_uuid}"
        self.uuid_y = f"y_axis_{_uuid}"
        self.uuid_data = f"data_{_uuid}"
        self.uuid_text = f"text_{_uuid}"

        # Create the line series in the view
        with dpg.group(parent=_parent,width=-1, height=-1):
            with dpg.group(horizontal=True):
                dpg.add_text(f"Current Value: ")
                dpg.add_text(f"-- {self.unit}", tag=self.uuid_text)
            with dpg.plot(no_title=True,no_inputs=True):
                # X axis
                dpg.add_plot_axis(dpg.mvXAxis,tag=self.uuid_x)
                dpg.set_axis_limits(self.uuid_x, 0.0, self.TIME_VIEW)

                # Y axis
                with dpg.plot_axis(dpg.mvYAxis, tag=self.uuid_y):
                    dpg.add_line_series([], [], label=self.name,tag=self.uuid_data)
                dpg.set_axis_limits_auto(self.uuid_y)
        # Set the visualization flag
        self.VIS_INIT = True
    
    def create_pp_measurements(self, manual:bool = False):
        """
            Creates state-estimation measurements from the component's Modbus values.

            Only keys from ``DICT_MEASUREMENT`` are considered. When ``manual=False``,
            the measurements are created directly in ``self.pp_net``; otherwise they are
            returned as a list of dictionaries.

            :param manual: Controls the output form (create directly or only collect)
            :type manual: bool
            :return: Empty list for direct creation or a list of manual measurement objects
            :rtype: list[dict]
        """
        measurements = []
        try:
            # Get measurement values from the dictionary entries that come from the ePHASORSIM network model
            for key,value in self.values.items():
                if not (key in self.DICT_MEASUREMENT and isinstance(value, ModbusValue)):
                    continue
                
                # Measurement variables
                measurement_type = self.DICT_MEASUREMENT[key]
                element_type = self.df_pp
                element = self.net_index
                std_dev = 0.0001
                value = value.value

                # Depending on the argument, decide whether pandapower should create the measurement with all checks or return 
                # a list of dictionary values for custom implementation
                if manual:
                    # Create measurement dictionary
                    measurements.append({
                        "name": None,
                        "measurement_type": measurement_type,
                        "element_type": element_type,
                        "element": element,
                        "value": value,
                        "std_dev": std_dev,
                        "side": None,
                    })
                else:
                    pp.create_measurement(
                        net=self.pp_net, 
                        meas_type=measurement_type,  # pyright: ignore[reportArgumentType]
                        element_type=element_type,   # pyright: ignore[reportArgumentType]
                        value=value,                 # pyright: ignore[reportArgumentType]
                        std_dev=std_dev, 
                        element=element)
        except Exception as e:
            print(f"SE_MEASUREMENT_ERROR - [{self.name}]: {e}")
        # Return the list of measurements
        return measurements

    def update_visualize(self):
        """
        Updates the default visualization with the current value and time axis.

        The method maintains the data buffers, updates the text and line series, and dynamically adjusts the visible axis limits.
        """
        # Check whether all DPG tag IDs are present
        if (self.uuid_text is None or
            self.uuid_x is None or
            self.uuid_data is None or
            self.uuid_y is None):
            print(f"ELEMENT_VISUALIZE - Grid element '{self.name}' could not be visualized because the DPG tag IDs were not properly initialized!")
            return
        
        # Update the current value and unit
        dpg.set_value(self.uuid_text, f"{self.value:.3f} {self.unit}")

        # Remember the first timestamp as reference
        now = time.time() # Current timestamp
        if not hasattr(self,"vis_start_time"):
            self.vis_start_time = now
        # Store the time relative to the start
        time_relative = (now - self.vis_start_time)
        self.data_time.appendleft(time_relative)  

        # X axis: newest value on the right, window scrolls to the right (show only the time interval)
        x_max = time_relative
        x_min = max(0.0, time_relative - self.TIME_VIEW)
        dpg.set_axis_limits(self.uuid_x, x_min, x_max)

        # Append the Y data value and filter to the plot range with padding (200%) 
        self.data_value.appendleft(self.value)
        t_visible, y_visible = self.__filter_line_series_data(self.data_value)
        # Update the visualization (DPG can also do this from the subthread)
        dpg.set_value(self.uuid_data, [t_visible, y_visible])
       
        # Automatically adjust the Y-axis scaling so all visible values stay in the window
        y_min = min(y_visible)
        y_max = max(y_visible)
        padding = (y_max - y_min) * 0.1 or 0.1
        dpg.set_axis_limits(self.uuid_y, y_min - padding, y_max + padding)
    
    def __filter_line_series_data(self, data_queue: deque[float]) -> tuple[list[float],list[float]]:
        """
        Filters data points to the current time window of the visualization.

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
