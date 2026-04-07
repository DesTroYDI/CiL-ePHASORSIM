from typing import Callable
import dearpygui.dearpygui as dpg
from NetConverter.PPtoePHASORSIM import Converter
import pandapower as pp
import copy, re

class DataGrid:
    TXT_STRING = 0
    TXT_INT = 1
    TXT_FLOAT = 2
    COMBO = 3
    CHECKBOX = 4
    GRID = 5
    COLOR = 6
    TXT_TEXT = 7
    
    def __init__(self, title, columns, dtypes, defaults, combo_lists = None, data=None):
        """
        Create a new DataGrid.

        :param title: Display title
        :param columns: List of column names.
        :param dtypes: List of data types for each column.
        :param defaults: List of default values for each column.
        :param combo_lists: List of combo lists for each column.
        :param data: 2D list for grid data, ordered data[col][row].
        """
        if not isinstance(columns, list) or not isinstance(dtypes, list) or not isinstance(defaults, list):
            raise ValueError("Columns, dtypes, and defaults must be lists.")
        
        if len(columns) != len(dtypes) or len(columns) != len(defaults):
            raise ValueError("Columns, dtypes, and defaults must have the same length.")

        if combo_lists is not None and (not isinstance(combo_lists, list) or len(columns) != len(combo_lists)):
            raise ValueError("Combo_lists must be a list with the same length as columns.")
        
        self.title = title
        self.columns = columns
        self.dtypes = dtypes
        self.defaults = defaults
        self.combo_lists = combo_lists or [None] * len(columns)
        self.data = data if data is not None else [[] for _ in columns]

    @property
    def shape(self):
        # follow pandas convention [rows, columns]
        return len(self.data[0] if self.data else 0), len(self.columns)

    def copy(self):
        ret = self.empty_like()
        ret.data = copy.deepcopy(self.data)
        return ret

    def empty_like(self):
        empty_grid = DataGrid(
            title = self.title,
            columns = [col for col in self.columns],
            dtypes = [dt for dt in self.dtypes],
            defaults = [val for val in self.defaults],
            combo_lists = [cl for cl in self.combo_lists]
        )
        return empty_grid

    def append(self, row):
        if row is None:
            row = self.defaults
        elif len(row) != len(self.columns):
            raise ValueError("Row does not match the column structure")
        for col in range(len(row)):
            if(isinstance(row[col], DataGrid)): # fails
                self.data[col].append(row[col].copy())
            else:
                self.data[col].append(row[col])

    def drop(self, row_idx):
        """Remove a row from the data grid by its index."""
        for col in range(len(self.columns)):
            if row_idx < len(self.data[col]):  # Make sure the row exists
                del self.data[col][row_idx]

    def swap_rows(self, row_idx_a, row_idx_b):
        if row_idx_a == row_idx_b:
            return

        if not (0 <= row_idx_a < len(self.data[0]) and 0 <= row_idx_b < len(self.data[0])):
            raise ValueError("Invalid row indices.")

        for column in self.data:
            column[row_idx_a], column[row_idx_b] = column[row_idx_b], column[row_idx_a]

    def get_row(self, row):
        return [col[row] for col in self.data]

    def get_cell(self, col_idx, row_idx):
        return self.data[col_idx][row_idx]
    
    def execute_callback(self, col_idx, row_idx):
        callback = self.callbacks[col_idx] 
        if callback:
            callback(self, row_idx)

    def display(self):
        for column in self.columns:
            print(f"{column:15s}", end=" ")
        print()
        
        for row in range(len(self.data[0])):
            for col in range(len(self.data)):
                if self.dtypes[col] == DataGrid.GRID:
                    print(f"{self.data[col][row].title:15s}", end=" ")
                else:
                    print(f"{str(self.data[col][row]):15s}", end=" ")
            print()

def swap_row_values(table_id, row_a_idx, row_b_idx):
    # Get the children of the table
    rows = dpg.get_item_children(table_id, 1)

    # Get the row IDs for the rows to be swapped
    row_a_id = rows[row_a_idx] 
    row_b_id = rows[row_b_idx] 

    # Get the cell IDs for each row
    cells_a = dpg.get_item_children(row_a_id, 1)
    cells_b = dpg.get_item_children(row_b_id, 1)

    # Temporarily store the values from row A
    temp_values = [dpg.get_value(cell) for cell in cells_a] 

    # Set the values in row A to the values from row B
    for i, cell in enumerate(cells_a):  
        dpg.set_value(cell, dpg.get_value(cells_b[i]))  

    # Set the values in row B to the temporarily stored values from row A
    for i, cell in enumerate(cells_b):  
        dpg.set_value(cell, temp_values[i])

# ------ Update by Gross, Hendrik -----------------
def swap_row_instruktionen(table_id, row_a_idx, row_b_idx, col_instruktion_idx):
    rows = dpg.get_item_children(table_id, 1)

    # Get data rows that should be swapped
    row_item_list1 = dpg.get_item_children(rows[row_a_idx])[1]  
    row_item_list2 = dpg.get_item_children(rows[row_b_idx])[1]  

    # Get combo box indices
    cb1_idx = row_item_list1[col_instruktion_idx]  
    cb2_idx = row_item_list2[col_instruktion_idx]  

    # Get existing instruction lists
    cb1_cfg = dpg.get_item_configuration(cb1_idx)
    cb2_cfg = dpg.get_item_configuration(cb2_idx)

    # Overwrite previous instruction lists
    dpg.configure_item(cb1_idx,items=cb2_cfg["items"])
    dpg.configure_item(cb2_idx,items=cb1_cfg["items"])
    # ------ End update Hendrik -----------------

def listEditCtrlDialog(grid: DataGrid, send_grid: Callable[[DataGrid], None]):
    """
    Creates a ListEditCtrl dialog.

    :param grid: The input data source for the control. 
    :param send_grid: Callback method to the parent control. 
    """    
    with dpg.window(label="Modal Dialog", 
                    modal=True, 
                    show=True, 
                    no_title_bar=True, 
                    pos=dpg.get_mouse_pos(local=False), 
                    width=530, 
                    height=480) as id_modal:
        
        table_id = dpg.generate_uuid()
        
        def _toggle_all_checkboxes():
            """Toggle all checkboxes in the table between checked and unchecked."""
            # Get all rows in the table
            row_ids = dpg.get_item_children(table_id)[1]    
            
            if not row_ids:
                return
            
            # Check if all checkboxes are currently checked
            all_checked = True
            for row_id in row_ids: 
                # Get all children of the row
                cell_ids = dpg.get_item_children(row_id)[1] 
                for cell_id in cell_ids:    
                    # Find checkboxes
                    if dpg.get_item_type(cell_id) == "mvAppItemType::mvCheckbox":
                        if not dpg.get_value(cell_id):
                            all_checked = False
                            break
                if not all_checked:
                    break
            
            # Toggle all checkboxes
            for row_id in row_ids:  
                cell_ids = dpg.get_item_children(row_id)[1] 
                for cell_id in cell_ids:    
                    if dpg.get_item_type(cell_id) == "mvAppItemType::mvCheckbox":
                        dpg.set_value(cell_id, not all_checked)
        
        # Filter
        dpg.add_text("Quick filter (applies to the entire data row)")
        with dpg.group(horizontal=True, width=0):
            dpg.add_input_text(hint="Enter quick filter...", user_data=table_id, callback=lambda s, a, u: dpg.set_value(u, dpg.get_value(s)))
            dpg.add_button(label="Select/Deselect all", callback=_toggle_all_checkboxes)
        
        get_grid,_ = listEditCtrl(table_id, grid, True, height=360)

        def on_ok():
            send_grid(get_grid())
            dpg.delete_item(id_modal)

        with dpg.group(horizontal=True):
            dpg.add_button(label="Ok", width=100, callback=on_ok)
            dpg.add_button(label="Cancel", width=100, callback=lambda: dpg.delete_item(id_modal))

def listEditCtrl(table_id, grid: DataGrid, use_filter=False, height=-1, allow_add=True, allow_delete=True, allow_movement=True, **kwargs):
    """
    Creates a ListEditCtrl widget.

    :param table_id: The ID for the table.
    :param grid: The input data source for the control. 
    """    

    # ------ Update by Gross, Hendrik -----------------
    # Expose network model object so object-related data can be read
    pp_net: pp.pandapowerNet | None = None
    def _ref_pp_net(_pp_net) -> None:
        nonlocal grid
        nonlocal pp_net
        pp_net = _pp_net

        # Update network-element objects only when configuration is available
        # If pandapower objects can be selected in the I/O configuration
        if grid.title.startswith("I/O Pins"):
            # Fill network elements in existing I/O config rows after setting the network model
            for idx in range(grid.shape[0]):
                _update_component(idx, True) 
        # If information about the referenced pandapower object should be displayed
        elif "Network Element" in grid.columns and not DataGrid.GRID in grid.dtypes:
            # Iterate through all rows and call _set_focus to refresh
            row_list = dpg.get_item_children(table_id)[1]
            for row_index in row_list:
                # Simulate that the net index has changed
                idx_net_index = grid.columns.index("PandaPower-NetIndex")
                row_item_list = dpg.get_item_children(row_index)[1]
                sender = dpg.get_item_alias(row_item_list[idx_net_index+1])   
                _set_focus(sender,None,row_index) 
    
    # Initially, update the element object list for a new row or the first row
    # _bSelected indicates whether newly loaded objects should be selected
    component_selected = False
    def _update_component(_row_index, _selected = False):
        nonlocal component_selected
        component_selected = _selected
        row_list = dpg.get_item_children(table_id)[1]
        user_data = row_list[_row_index]

        # Determine column indices for object list and instructions
        idx_element = grid.columns.index("Network Element")

        row_item_list = dpg.get_item_children(user_data)[1]
        sender = dpg.get_item_alias(row_item_list[idx_element+1])
        app_data = grid.combo_lists[idx_element][grid.data[idx_element][_row_index]]
        _set_focus(sender,app_data,user_data)
        
    # ------ End update -----------------

    def _grid_ref():
        nonlocal grid
        return grid

    def _subgrid_callback(col_idx, row_idx, new_grid: DataGrid):
            """
            Callback method for child grids to update their data in the parent grid.
            """
            nonlocal grid
            grid.data[col_idx][row_idx] = new_grid

    def _add_row(use_defaults=True): 
        """
        Adds a new row to the DataGrid. 

        :param use_defaults: A boolean indicating whether to use default values for the new row. 
            If False, it uses the data from the corresponding row in the underlying DataGrid.

        This function creates a new row in the DataGrid and populates it with widgets appropriate for each column's 
        data type. The widgets are initialized with either default values (if use_defaults=True) or with the 
        corresponding data from the underlying DataGrid (if use_defaults=False).

        It uses the _set_focus callback to update the selected row index when any widget in the new row is clicked.

        If a new row is added that exceeds the current number of rows in the underlying DataGrid, 
        the DataGrid is expanded with a row of default values.

        :raises ValueError: If a column has an unsupported data type.
        """
        nonlocal pp_net
        nonlocal grid
        nonlocal table_id
        nonlocal focus_index

        row_idx = len(dpg.get_item_children(table_id)[1])

        # if the row_idx is greater than the grid length, then expand the grid
        if row_idx >= grid.shape[0]:
            grid.append(grid.defaults)

        if focus_index < 0:
            focus_index = 0

        # ------ Update by Gross, Hendrik -----------------
        # Filter key
        # Filter reads the data row and builds a string used by quick filter
        _filter_key = ""
        if use_filter == True:
            _filter_key = str(_grid_ref().get_row(row_idx))
        # ------ End update -----------------

        # need to feed in the row index for the callbacks
        with dpg.table_row(parent = table_id, filter_key=_filter_key) as row_id:

            dpg.add_table_cell()

            for col_idx in range(len(grid.columns)):
                row = grid.defaults if use_defaults else _grid_ref().get_row(row_idx) 

                if grid.dtypes[col_idx] == DataGrid.CHECKBOX:
                    dpg.add_checkbox(callback=_set_focus, 
                                     default_value=row[col_idx], 
                                     user_data=row_id)
                elif grid.dtypes[col_idx] == DataGrid.TXT_STRING:
                    id_input_text = dpg.generate_uuid()
                    dpg.add_input_text(tag=id_input_text, 
                                       default_value=row[col_idx], 
                                       hint="Enter text here", width=-1, callback=_set_focus, user_data=row_id)
                    # ------ Update by Gross, Hendrik -----------------
                    # Support for "add_input_int" plus logic that
                    # reads information from a pandapower object and writes it to this column
                elif grid.dtypes[col_idx] == DataGrid.TXT_INT:
                    if grid.columns[col_idx] == "PandaPower-NetIndex":
                        id_input_int = f"PP_INFO_{dpg.generate_uuid()}"
                    else:
                        id_input_int = dpg.generate_uuid()
                    dpg.add_input_int(tag=id_input_int, 
                                       default_value=row[col_idx], 
                                       width=-1, callback=_set_focus, user_data=row_id)
                    _register_widget_click(id_input_int, row_id)
                    # Support for "add_input_float"
                elif grid.dtypes[col_idx] == DataGrid.TXT_FLOAT:
                    id_input_float = dpg.generate_uuid()
                    dpg.add_input_float(tag=id_input_float, 
                                       default_value=row[col_idx], 
                                       width=-1, callback=_set_focus, user_data=row_id)
                    _register_widget_click(id_input_float, row_id)
                elif grid.dtypes[col_idx] == DataGrid.COMBO:
                    # The second combo box must be identifiable so instructions can be loaded dynamically
                    if grid.title.startswith("I/O Pins") and grid.columns[col_idx] == "Network Element":
                        id_input_combo = f"CB_NETZELEMENT_{dpg.generate_uuid()}"
                    elif grid.columns[col_idx] == "Network Element" and not(DataGrid.GRID in grid.dtypes):
                        id_input_combo = f"PP_INFO_{dpg.generate_uuid()}"
                    else:
                        id_input_combo = dpg.generate_uuid()
                    # ------ End update -----------------
                    dpg.add_combo(tag=id_input_combo, 
                                  items=grid.combo_lists[col_idx], 
                                  default_value=grid.combo_lists[col_idx][row[col_idx]], 
                                  no_preview=False, width=-1, callback=_set_focus, user_data=row_id)
                    _register_widget_click(id_input_combo, row_id)
                elif grid.dtypes[col_idx] == DataGrid.COLOR:
                    id_color_pikr = dpg.generate_uuid()
                    dpg.add_color_edit(tag=id_color_pikr, 
                                       default_value=row[col_idx], 
                                       no_inputs=True, callback=_set_focus, user_data=row_id)
                    _register_widget_click(id_color_pikr, row_id)
                elif grid.dtypes[col_idx] == DataGrid.GRID:
                    id_button = dpg.generate_uuid()

                    dpg.add_button(tag=id_button,
                                   label="Configure", 
                                   callback=call_component_subgrid,
                                   user_data=row_id, 
                                   id=f"{id_button}_{col_idx}") # For identifying the column
                    # ------ Update by Gross, Hendrik -----------------
                    # Support for "add_text"
                elif grid.dtypes[col_idx] == DataGrid.TXT_TEXT:
                    id_text = dpg.generate_uuid()
                    dpg.add_text(tag=id_text, default_value=row[col_idx])
                    _register_widget_click(id_text, row_id)
                    # ------ End update -----------------
                else:
                    raise ValueError("unsupported data type")
                
            # close out the row
            dpg.add_selectable(height=20, span_columns=True, callback=_set_focus, user_data=row_id)
        
        # ------ Update by Gross, Hendrik -----------------
        # Append network element objects for a new row (not in popup)
        if grid.title.startswith("I/O Pins") and pp_net is not None:
            _update_component(row_idx, False)
        # ------ End update -----------------

    # ------ Update by Gross, Hendrik -----------------
    # Callback for configure button that opens the network element object list
    def call_component_subgrid(sender, app_data, user_data):
        """Callback function for configure button"""
        nonlocal focus_index
        col_idx = int(sender.split('_')[-1])    # Determine column from sender (ID)
        
        # Determine index of the data row
        dpg.unhighlight_table_row(table_id, focus_index)
        table_children = dpg.get_item_children(table_id, 1)
        focus_index = table_children.index(user_data)
        dpg.highlight_table_row(table_id, focus_index, [15,86,135])

        listEditCtrlDialog(
            grid=_grid_ref().data[col_idx][focus_index],
            send_grid=lambda new_grid: _subgrid_callback(col_idx, focus_index, new_grid)
        )
     # ------ End update -----------------

    def _delete_row():
        nonlocal focus_index
        nonlocal table_id
        if focus_index < 0 or len(dpg.get_item_children(table_id)[1]) < 2:
            return
        
        # delete the row from DPG
        row_id = dpg.get_item_children(table_id)[1][focus_index]
        dpg.delete_item(row_id)

        # delete the row from the grid
        grid.drop(focus_index)

        # move the focus_index up if list length is less than focus_index
        if(focus_index >= len(dpg.get_item_children(table_id)[1])):
            focus_index -= 1
        # call _set_focus on the current index
        if(focus_index >= 0):
            dpg.highlight_table_row(table_id, focus_index, [15,86,135])

    def _move_row_up():
        nonlocal focus_index
        nonlocal table_id

        row_ids = dpg.get_item_children(table_id, 1)
        if (focus_index == 0) or (len(row_ids) <= 1):
            return False
        
        swap_row_values(table_id, focus_index, focus_index-1)
        grid.swap_rows(focus_index, focus_index-1) 
        
        # ------ Update by Gross, Hendrik -----------------
        # If an instruction list exists (I/O configuration), update it
        if grid.title.startswith("I/O Pins"):
            swap_row_instruktionen(table_id,focus_index, focus_index-1, (grid.columns.index("Instruction")+1))
        # ------ End update Hendrik -----------------

        dpg.unhighlight_table_row(table_id, focus_index)
        focus_index -= 1
        dpg.highlight_table_row(table_id, focus_index, [15,86,135])

        return True

    def _move_row_down():
        nonlocal focus_index
        nonlocal table_id

        row_ids = dpg.get_item_children(table_id, 1)
        if (focus_index == len(row_ids)-1) or (len(row_ids) <= 1):
            return False
        
        swap_row_values(table_id, focus_index, focus_index+1)
        grid.swap_rows(focus_index, focus_index+1)

        # ------ Update by Gross, Hendrik -----------------
        # If an instruction list exists (I/O configuration), update it
        if grid.title.startswith("I/O Pins"):
            swap_row_instruktionen(table_id,focus_index, focus_index+1, (grid.columns.index("Instruction")+1))
        # ------ End update Hendrik -----------------

        dpg.unhighlight_table_row(table_id, focus_index)
        focus_index += 1
        dpg.highlight_table_row(table_id, focus_index, [15,86,135])
        return True

    focus_index=0
    def _set_focus(sender, app_data, user_data): 
        if (dpg.get_item_type(sender) == "mvAppItemType::mvSelectable"):
            dpg.set_value(sender, False)
        nonlocal focus_index
        nonlocal table_id
        dpg.unhighlight_table_row(table_id, focus_index)
        table_children = dpg.get_item_children(table_id, 1)
        focus_index = table_children.index(user_data)
        dpg.highlight_table_row(table_id, focus_index, [15,86,135])

        # ------ Update by Gross, Hendrik -----------------
        # If the network element combo box changes, reload instructions
        # and also reload the object list in the associated grid
        nonlocal component_selected
        if str(sender).startswith("CB_NETZELEMENT"):
            # Determine column indices
            idx_instruction = grid.columns.index("Instruction")
            row_item_list = dpg.get_item_children(table_children[focus_index])[1]
            cb_value = dpg.get_value(row_item_list[idx_instruction+1])

            # Update instructions
            _instruction_list = ["-"]
            _component_list = []
            for component in Converter.COMPONENTS:
                if component.__name__ == app_data:
                    _instruction_list = component.instruction_list
                    _component_list = component.load_from_pp_net(pp_net)
                    break
                    # Set instruction value
            idx_instruktion = grid.columns.index("Instruction")
            dv = _instruction_list[grid.data[idx_instruktion][focus_index]]
            if cb_value in _instruction_list:
                dv = cb_value
            dpg.configure_item(row_item_list[idx_instruction+1], items=_instruction_list)
            dpg.configure_item(row_item_list[idx_instruction+1], default_value=dv)
            
            # Update objects
            _data = [[],[],[]]
            for component in _component_list:                
                _data[0].append(component_selected)
                _data[1].append(component.id)
                _data[2].append(component.to_row())
            grid.data[4][focus_index].data = _data

            component_selected = False   # Reset
        # ------ End update Hendrik -----------------
        # ------ Update by Gross, Hendrik -----------------
        # If net index, pandapower object, or class changes,
        # update the object information.
        # These values do not need to exist in the data grid because they are display-only information
        if str(sender).startswith("PP_INFO"):
            row_item_list = dpg.get_item_children(table_children[focus_index])[1]

            # Note: +1 is used because row_item_list contains all columns plus index column
            pp_obj_info = "No object information could be determined in pandapower."
            pp_df_name = "<None>"
            idx_info = grid.columns.index("Object Information [*]")        # Column index for displaying object information
            idx_df = grid.columns.index("PandaPower-DataFrame [*]")     # Column index for displaying dataframe string
            try:
                # Determine column indices
                idx_element = grid.columns.index("Network Element")                 # Column index of element combo box
                idx_net_index = grid.columns.index("PandaPower-NetIndex")        # Column index of pandapower net index
                
                # Determine network element (bus, load) and dataframe name from index
                pp_element_name = dpg.get_value(row_item_list[idx_element+1])
                pp_df_index = grid.combo_lists[idx_element].index(pp_element_name)
                pp_df_name = grid.combo_lists[idx_df][pp_df_index]       # Determine correct dataframe from combo list
                
                # Read dataframe index from control
                element_net_index = dpg.get_value(row_item_list[idx_net_index+1])
                # Read object information and write into column
                str_pp_obj = str(getattr(pp_net,pp_df_name).loc[element_net_index])
                pp_obj_info = re.sub(r'\s+', " ", str_pp_obj.replace("\n","; ")) 
            except:
                pass
            dpg.set_value(row_item_list[idx_info+1],pp_obj_info)
            dpg.set_value(row_item_list[idx_df+1],pp_df_name)

        # ------ End update Hendrik -----------------
    
    def _on_widget_click(row_id):  
            nonlocal focus_index
            nonlocal table_id
            dpg.unhighlight_table_row(table_id, focus_index)
            # this is slow but good enough for prototyping
            table_children = dpg.get_item_children(table_id, 1)
            focus_index = table_children.index(row_id)
            # print(table_children, row_id, focus_index)
            dpg.highlight_table_row(table_id, focus_index, [15,86,135])
            # highlight_row(table_id, focus_index)

    def _register_widget_click(sender, row_id):
        handler_tag = f"{row_id} handler"
        if not dpg.does_item_exist(handler_tag):
            with dpg.item_handler_registry(tag=handler_tag) as handler:
                dpg.add_item_clicked_handler(callback=lambda x: _on_widget_click(row_id)) 

        dpg.bind_item_handler_registry(sender, handler_tag)

    with dpg.child_window(menubar=True, height=height):
        with dpg.menu_bar():
                    dpg.add_text(grid.title)
        # ------ Update by Gross, Hendrik -----------------
        # Show buttons only in main control; skip inside popup dialog
        if height < 0 and (allow_add or allow_delete or allow_movement or use_filter):
            with dpg.group(horizontal=True):
                if allow_add:
                    dpg.add_button(label="Add", tag=dpg.generate_uuid(), callback=lambda: _add_row(use_defaults=True))
                if allow_delete:
                    dpg.add_button(label="Remove", tag=dpg.generate_uuid(), callback=_delete_row)
                if allow_movement:
                    dpg.add_button(arrow=True, direction=dpg.mvDir_Up, callback=_move_row_up)
                    dpg.add_button(arrow=True, direction=dpg.mvDir_Down, callback=_move_row_down)
                if use_filter:
                    dpg.add_input_text(hint="Enter quick filter...", user_data=table_id, callback=lambda s, a, u: dpg.set_value(u, dpg.get_value(s)))
        # ------ End update -----------------
        with dpg.child_window():
            with dpg.table(tag=table_id, header_row=True, resizable=True, policy=dpg.mvTable_SizingStretchProp,
                           row_background=False, no_host_extendX=True, no_pad_innerX=True,
                           borders_outerH=True, borders_innerV=True, borders_outerV=True,pad_outerX=True,context_menu_in_body=False):

                dpg.add_table_column() # index column
                for col in grid.columns:
                    dpg.add_table_column(label=col)
                dpg.add_table_column() # selector column

                for i in range(len(grid.data[0])):
                    _add_row(use_defaults=False)

    def evaluate_grid():
        nonlocal grid
        # create a new grid of the same structure
        new_grid = grid.empty_like()
        
        # populate the grid from the table
        for row_idx, row_id in enumerate(dpg.get_item_children(table_id)[1]):
            new_row = []
            cells = list(dpg.get_item_children(row_id)[1])

            # Temporary variable for caching instructions for an object class
            _instruction_list = []
            _followed_cols = 10

            for col_idx, col_id in enumerate(cells[1:-1]):  # Skip the first and last cell.
                if grid.dtypes[col_idx] == DataGrid.GRID:
                    # Get subgrid from grid
                    new_row.append(grid.get_cell(col_idx, row_idx))
                elif grid.dtypes[col_idx] == DataGrid.COMBO:
                    selection = dpg.get_value(col_id)
                    
                    # ------ Update by Gross, Hendrik -----------------
                    # Fetch instructions for matching against the following column
                    _alias = dpg.get_item_alias(col_id)
                    if _alias.startswith("CB_NETZELEMENT"):
                        for component in Converter.COMPONENTS:
                            if component.__name__ == selection:
                                _instruction_list = component.instruction_list
                                _followed_cols = 0
                                break
                    
                    if _followed_cols == 1:
                        # Following column contains instructions for the network element
                        idx = _instruction_list.index(selection)
                    else:
                        idx = grid.combo_lists[col_idx].index(selection) # pyright: ignore[reportOptionalMemberAccess]
                    _followed_cols += 1
                    # ------ End update -----------------
                    new_row.append(idx)
                else:
                    # Get the value in the cell and append it to the new row.
                    new_row.append(dpg.get_value(col_id))
            # Add the new row to the data in the new grid.
            new_grid.append(new_row)

        return new_grid
    return evaluate_grid, _ref_pp_net