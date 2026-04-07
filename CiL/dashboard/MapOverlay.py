# -*- coding: utf-8 -*-
"""UI layer that can render the PandaPower network model and the legend above the map"""
import json, math
from copy import deepcopy

import numpy as np
import pandapower as pp
import dearpygui.dearpygui as dpg
from ..map.geo import Coordinate


class MapOverlayRenderer:
    """
    Renders network elements and hover information as an overlay on a DPG map.
    """

    # --------------------------------------------------------------------------------------------------------
    # Visualization constants
    RADIUS_BUS: float           = 5.0
    THICKNESS_LINE: float       = 2.0
    THICKNESS_EXTGTRID: float   = 2.0

    # Number of frames after which hover information should be updated
    HOVER_UPDATE_FRAMES: int    = 15
    # Distances at which hover information should be retrieved (bus first, then line)
    BEST_BUS_DISCTANCE: float   = 10.0
    BEST_LINE_DISTANCE: float   = 8.0

    # Fixed color definitions for certain operating states
    COL_EXTGRID     = (230, 140, 40, 255)
    COL_ERROR       = (163, 45, 45, 255)
    COL_OPEN        = (110, 110, 110, 255)

    # Color definitions (colormap) for voltage and loading states.
    CMAP = [    
        (0, 60, 200, 255),    # blue
        (0, 200, 220, 255),   # cyan
        (170, 230, 80, 255),  # green
        (255, 200, 0, 255),   # yellow
        (180, 0, 0, 255),     # red
    ]
    # Thresholds for buses and lines
    MIN_MAX_BUS: tuple[float,float]     = (0.9, 1.1)
    MIN_MAX_LINE: tuple[float,float]    = (0.0, 100.0)

    def __init__(self, pp_net: pp.pandapowerNet, map_widget, map_drawlist_tag: int, hover_text_tag: int | None = None):
        """
        Initialize the overlay renderer with network and map references.

        :param pp_net: Pandapower network model
        :type pp_net: pp.pandapowerNet
        :param map_widget: Map widget with tile manager
        :param map_drawlist_tag: Drawlist tag used for hover detection
        :type map_drawlist_tag: int
        :param hover_text_tag: Optional text widget for hover output
        :type hover_text_tag: int | None
        """
        # References to the pandapower network model and map widget.
        self.pp_net = pp_net

        # Map widget to draw into
        self.map_widget = map_widget
        # UI container
        if map_drawlist_tag is None or not dpg.does_item_exist(map_drawlist_tag):
            raise ValueError("DPG_DRAWLIST_NONE - No drawlist available!")
        self.map_drawlist_tag = map_drawlist_tag    
        # Target text field for hover output.
        self.hover_text_tag = hover_text_tag

        # Parent node for the UI layer where network elements are drawn on the map
        parent_node = getattr(self.map_widget.tile_manager, "overlay_draw_node_id", None)
        if parent_node is None:
            raise ValueError("DPG_PANDAPOWER_MAPLAYER - No UI layer for pandapower network elements is available on the map")
        self.parent_node = parent_node

        # Parent node for the legend UI layer
        legend_node = getattr(self.map_widget.tile_manager, "ui_draw_node_id", None)
        if legend_node is None:
            raise ValueError("DPG_PANDAPOWER_MAPLAYER - No UI layer for the legend is available on the map")
        self.legend_node = legend_node

        # Draw tags for legend elements (to avoid multiple overlapping redraws during resize/rebuild)
        self._legend_draw_tags: list[int] = []

        # Storage for network nodes (DPG ID; value; coordinates)
        self._map_bus_draw_tags: dict[int, int] = {}
        self._map_bus_latlon: dict[int, tuple[float, float]] = {}

        # Storage for lines (DPG ID; value; coordinates)
        self._map_line_draw_tags: dict[int, list[int]] = {}
        self._map_line_latlon: dict[int, list[tuple[float, float]]] = {}

        # Storage for external grids (DPG ID; coordinates)
        self._map_ext_grid_draw_tags: list[int] = []
        
        # Storage for last switch states and disconnected lines
        self._switch_last_states: list[bool]= []
        self._switch_disconnected_line: list[int] = []

        # Last known zoom level
        self._map_last_zoom: int | None = None

    # --------------------------------------------------------------------------------------------------------
    # Public methods
    def build_overlay(self):
        """Rebuild the map overlay (lines, ext_grid, buses)."""
        # Reset overlay data
        self._map_bus_draw_tags = {}
        self._map_bus_latlon = {}
        self._map_line_draw_tags = {}
        self._map_line_latlon = {}
        self._map_ext_grid_draw_tags = []
        
        # Store zoom level
        self._map_last_zoom = self.map_widget.zoom_level

        # Compute all node coordinates, since they are also used by other
        # network elements (e.g., ext_grid)
        tile_size = self.map_widget.tile_manager.tile_server.tile_size
        bus_canvas_points = self._collect_bus_canvas_points(self._map_last_zoom, tile_size)
        line_canvas_points = self._collect_line_canvas_points(self._map_last_zoom, tile_size)

        # Draw all lines
        for line_idx, row in self.pp_net.line.iterrows():
            # Get all coordinates of the line
            line_coords = line_canvas_points.get(line_idx, [])
            while len(line_coords) >= 2:
                # Draw line segment
                draw_tag = dpg.generate_uuid()
                dpg.draw_line(
                    p1=line_coords[0],
                    p2=line_coords[1],
                    thickness=self.THICKNESS_LINE,
                    parent=self.parent_node,
                    tag=draw_tag
                )
                # Store line segment
                if line_idx not in self._map_line_draw_tags:
                    self._map_line_draw_tags[line_idx] = []
                self._map_line_draw_tags[line_idx].append(draw_tag)
                
                line_coords.pop(0)

        # Draw external grids
        for _, row in self.pp_net.ext_grid.iterrows():
            bus_idx = row.get("bus")
            if bus_idx not in bus_canvas_points:
                continue

            x, y = bus_canvas_points[bus_idx]
            draw_tag = dpg.generate_uuid()
            # Draw rectangle around node with external grid
            rect_size = self.RADIUS_BUS * 1.5
            dpg.draw_rectangle(
                pmin=(x - rect_size, y - rect_size),
                pmax=(x + rect_size, y + rect_size),
                color=self.COL_EXTGRID,
                fill=self.COL_EXTGRID,
                thickness=self.THICKNESS_EXTGTRID,
                parent=self.parent_node,
                tag=draw_tag
            )
            # Store data
            self._map_ext_grid_draw_tags.append(draw_tag)

        # Draw all network nodes
        for bus_idx, point in bus_canvas_points.items():
            draw_tag = dpg.generate_uuid()
            dpg.draw_circle(
                center=point,
                radius=self.RADIUS_BUS,
                fill=(255,255,255,255),
                parent=self.parent_node,
                tag=draw_tag,
            )
            # Store data
            self._map_bus_draw_tags[bus_idx] = draw_tag

        # Create frame callback (more frequent hover info updates)
        def hover_info_callback():
            # Update map layer
            self._update_map_overlay()
            # Update hover info
            self._update_hover_info()
            
            # Call again after N frames
            dpg.set_frame_callback(
                frame=dpg.get_frame_count() + self.HOVER_UPDATE_FRAMES,
                callback=hover_info_callback
            )
        dpg.set_frame_callback(frame=1, callback=hover_info_callback)

    def build_legend(self):
        """Create or update the fixed legend in the lower-right map corner."""
        # Delete old legend
        self._delete_draw_tags(self._legend_draw_tags)
        self._legend_draw_tags = []

        # Map size
        view_w = int(self.map_widget.width)
        view_h = int(self.map_widget.height)

        # Layout constants (percentage-based, depending on map size)
        margin_y = int(view_w * 0.02) # Distance to bottom edge
        margin_x = int(view_w * 0.05) # Distance to side edge
        bar_w =int(view_w * 0.03)  # Bar width 3%
        bar_h = int(view_h * 0.4)  # Bar height 50%
        gap = int(view_w * 0.05)    # Gap between bars 5%

        # Bar positions (lower right)
        y_bottom = view_h - margin_y
        y_top = y_bottom - bar_h

        x_line_1 = view_w - margin_x
        x_line_0 = x_line_1 - bar_w

        x_bus_1 = x_line_0 - gap
        x_bus_0 = x_bus_1 - bar_w

        # Background box
        bg_x0 = x_bus_0 -  int(view_w * 0.02)
        bg_y0 = y_top - int(view_h * 0.02)

        tag = dpg.generate_uuid()
        dpg.draw_rectangle(
            pmin=(bg_x0, bg_y0),
            pmax=(view_w, view_h),
            fill=(245, 245, 245, 220),
            color=(160, 160, 160, 180),
            parent=self.legend_node,
            tag=tag
        )
        self._legend_draw_tags.append(tag)

        # Scale bars
        # Bus voltage
        self._draw_colorbar(
            x0=x_bus_0,  x1=x_bus_1,
            y0=y_top, y1=y_bottom,
            vmin=self.MIN_MAX_BUS[0],
            vmax=self.MIN_MAX_BUS[1],
            title="Bus\nVoltage\n[pu]"
        )

        # Line loading
        self._draw_colorbar(
            x0=x_line_0, x1=x_line_1,
            y0=y_top, y1=y_bottom,
            vmin=self.MIN_MAX_LINE[0],
            vmax=self.MIN_MAX_LINE[1],
            title="Line\nLoading\n[%]"
        )

    def zoom_to_network(self, padding_px: int = 10) -> bool:
        """Zoom the map so that all buses are visible in the viewport."""

        # Collect valid bus geocoordinates (skip None entries)
        bus_latlon = [
            (lon, lat)
            for _, row in self.pp_net.bus.iterrows()
            if row.get("geo",None) is not None
            for lon, lat in [self._extract_lat_lon(row.get("geo"))[0]]
        ]

        if not bus_latlon:
            return False

        # Compute available pixel area minus padding
        view_w = max(1, int(self.map_widget.width))
        view_h = max(1, int(self.map_widget.height))
        fit_w  = max(1, view_w - 2 * padding_px)
        fit_h  = max(1, view_h - 2 * padding_px)
        tile_size = self.map_widget.tile_manager.tile_server.tile_size
        max_zoom  = self.map_widget.tile_manager.tile_server.max_zoom_level

        def _bounds(z: int) -> tuple[float, float, float, float]:
            """Return the pixel bounding box of all buses for a zoom level."""
            px = [
                (Coordinate.from_latlon(lat, lon).tile_xy(z, floor_=False)[0] * tile_size[0],
                Coordinate.from_latlon(lat, lon).tile_xy(z, floor_=False)[1] * tile_size[1])
                for lon, lat in bus_latlon
            ]
            xs, ys = zip(*px)
            return min(xs), max(xs), min(ys), max(ys)

        # Find the highest zoom level where all buses still fit in the viewport
        best_zoom, best_bounds = next(
            ((z, b) for z in range(max_zoom, -1, -1)
            if (b := _bounds(z)) and b[1] - b[0] <= fit_w and b[3] - b[2] <= fit_h),
            (0, _bounds(0)),  # Fallback: zoom level 0 if nothing fits
        )

        # Convert bounding-box center to normalized map coordinates
        min_x, max_x, min_y, max_y = best_bounds
        scale = float(2 ** best_zoom)
        center = Coordinate(
            (min_x + max_x) / (2 * tile_size[0] * scale),
            (min_y + max_y) / (2 * tile_size[1] * scale),
        )

        # Set zoom and map viewport, shifting the origin to the upper-left corner
        self.map_widget.zoom_level = best_zoom
        self.map_widget.origin = center.with_screen_offset(
            -view_w / 2, -view_h / 2,
            zoom=best_zoom, resolution=tile_size,
        )
        self.map_widget.tile_manager.set_origin(self.map_widget.origin, best_zoom)
        self.map_widget.draw_layers()

        # Rebuild overlay for the new zoom state
        self._map_last_zoom = None
        self._update_map_overlay()
        return True

    # --------------------------------------------------------------------------------------------------------
    # Color mapping method (can theoretically be overridden), or adjust colormap/min-max values
    def _get_color(self, _min:float, _max:float, _value:float):
        """Interpolate a color from ``CMAP`` for the given value range."""
        # Clamp value to range
        value = max(_min, min(_max, _value))

        # Normalize to [0, 1]
        t = (value - _min) / (_max - _min)
        # Map to colormap segments
        col_segments = len(self.CMAP) - 1
        pos = t * col_segments
        col_idx = int(pos)

        # Edge case: exactly at upper end
        if col_idx >= col_segments:
            return self.CMAP[-1]

        # Get interpolated color
        local_t = pos - col_idx
        return self._lerp_color(self.CMAP[col_idx], self.CMAP[col_idx + 1], local_t)

    # --------------------------------------------------------------------------------------------------------
    # Update methods (network model and hover)
    def _update_map_overlay(self):
        """Update colors/states and rebuild overlay when the zoom changes."""
        # Check whether the map has changed
        current_zoom = self.map_widget.zoom_level
        if self._map_last_zoom != current_zoom:
            # Delete existing DearPyGui objects by their tags
            self._delete_draw_tags(self._map_bus_draw_tags.values())
            self._delete_draw_tags(self._map_line_draw_tags.values())
            self._delete_draw_tags(self._map_ext_grid_draw_tags)
            self.build_overlay()
            self.build_legend()

        # Evaluate all open disconnection points (gray line coloring), only if switch states changed since the last cycle
        if not np.array_equal(self._switch_last_states, self.pp_net.switch["closed"].values):
            # Store new switch states
            self._switch_last_states = deepcopy(self.pp_net.switch["closed"].values)
            self._switch_disconnected_line = []

            # Find and define disconnected lines
            for _, row in self.pp_net.switch.iterrows():
                # Visualize only open switches
                if bool(row.get("closed", True)):
                    continue

                # ePHASORSIM model: bus-bus switch; "element" is the bus where the disconnected line is connected
                bus_idx = row["element"]
                line_at_bus = self.pp_net.line[(self.pp_net.line["from_bus"] == bus_idx) | (self.pp_net.line["to_bus"] == bus_idx)]
                self._switch_disconnected_line += line_at_bus.index.tolist()

        # Color all lines by loading
        for line_idx, draw_tags in self._map_line_draw_tags.items():
            try:
                # If line is at an open disconnector, show it in gray
                if line_idx in self._switch_disconnected_line:
                    color = self.COL_OPEN
                else:
                    # Min/max/current value
                    loading_percent_min = self.MIN_MAX_LINE[0]
                    loading_percent_max = self.MIN_MAX_LINE[1]
                    loading_percent = self.pp_net.res_line.at[line_idx, "loading_percent"]

                    # Interpolated color value
                    color = self._get_color(loading_percent_min,loading_percent_max,loading_percent)
            except:
                color = self.COL_ERROR
            # Color all line segments equally
            for draw_tag in draw_tags:
                dpg.configure_item(draw_tag, color=color)
        
        # Color all network nodes by voltage magnitude
        for bus_idx, draw_tag in self._map_bus_draw_tags.items():
            try:
                # Min/max/current value
                vm_pu_min = self.MIN_MAX_BUS[0]
                vm_pu_max = self.MIN_MAX_BUS[1]
                vm_pu = self.pp_net.res_bus.at[bus_idx, "vm_pu"]

                # Interpolated color value
                color = self._get_color(vm_pu_min,vm_pu_max,vm_pu)
            except:
                color = self.COL_ERROR
            dpg.configure_item(draw_tag, color=color, fill=color)               

    def _update_hover_info(self):
        """
        Determine the nearest object to the mouse position and set hover text.

        Priority: bus first, then line.
        """
        if self.hover_text_tag is None or not dpg.does_item_exist(self.hover_text_tag):
            return

        # Mouse position relative to drawlist
        if not dpg.is_item_hovered(self.map_drawlist_tag):
            dpg.set_value(self.hover_text_tag, "-")
            return 

        mouse_x, mouse_y = dpg.get_mouse_pos(local=False)
        rect_x, rect_y = dpg.get_item_rect_min(self.map_drawlist_tag)

        # Determine map position
        canvas_x = mouse_x - rect_x
        canvas_y = mouse_y - rect_y
        zoom = self.map_widget.zoom_level
        tile_size = self.map_widget.tile_manager.tile_server.tile_size

        mouse_coord = self.map_widget.get_coordinate(canvas_x, canvas_y)
        mouse_tile_x, mouse_tile_y = mouse_coord.tile_xy(zoom, floor_=False)
        mouse_px = mouse_tile_x * tile_size[0]
        mouse_py = mouse_tile_y * tile_size[1]

        # Check whether hovering over a network node
        best_bus = None
        best_bus_dist = float("inf")
        for bus_idx, latlon in self._map_bus_latlon.items():
            bx, by = self._tile_pixel_from_latlon(latlon[0], latlon[1], zoom, tile_size)
            dist = math.hypot(mouse_px - bx, mouse_py - by)
            if dist < best_bus_dist:
                best_bus_dist = dist
                best_bus = bus_idx

        # Check whether node-distance threshold is valid for display
        # Then retrieve data from the pandapower network model
        if best_bus is not None and best_bus_dist <= self.BEST_BUS_DISCTANCE:
            try:
                # Determine result values
                vm_pu = self.pp_net.res_bus.at[best_bus, "vm_pu"]
                vm_perc = -(1 - vm_pu) * 100 
                # Determine base voltage
                base_kv = self.pp_net.bus.at[best_bus, "vn_kv"]
                # Determine powers at node
                p_mw = self.pp_net.res_bus.at[best_bus, "p_mw"]
                q_mvar = self.pp_net.res_bus.at[best_bus, "q_mvar"]
                # Build text output
                text = (
                    f"Bus '{best_bus}' --> "
                    f"U={(vm_pu * base_kv):.3f} kV ({vm_pu:.3f} p.u., {vm_perc:.1f} %) | "
                    f"Power: P={p_mw:.3f} MW; Q={q_mvar:.3f} Mvar"
                )
            except Exception as e:
                text = f"Bus '{best_bus}' - Error while reading results: {e}"
            dpg.set_value(self.hover_text_tag, text)
            return

        # Check whether hovering over a line
        best_line = None
        best_line_dist = float("inf")
        for line_idx, list_latlon in self._map_line_latlon.items():
            _line_latlon = deepcopy(list_latlon)
            while len(_line_latlon)>=2:
                # Determine start/end points of line segment
                ax, ay = self._tile_pixel_from_latlon(_line_latlon[0][0], _line_latlon[0][1], zoom, tile_size)
                bx, by = self._tile_pixel_from_latlon(_line_latlon[1][0], _line_latlon[1][1], zoom, tile_size)
                _line_latlon.pop(0)

                # Check distance
                dist = self._point_segment_distance(mouse_px, mouse_py, ax, ay, bx, by)
                if dist < best_line_dist:
                    best_line_dist = dist
                    best_line = line_idx

        # Check whether line-distance threshold is valid for display
        # Then retrieve data from the pandapower network model
        if best_line is not None and best_line_dist <= self.BEST_LINE_DISTANCE:
            try:
                name = self.pp_net.line.at[best_line, "name"]
                if best_line in self._switch_disconnected_line:
                    # Show only information about open switching state
                    text = f"'{name}' --> Open disconnector on this line (no loading)"
                else:
                    # Show line results
                    load_pct = self.pp_net.res_line.at[best_line, "loading_percent"]
                    i_ka = self.pp_net.res_line.at[best_line, "i_ka"]
                    text = f"'{name}' --> Loading={load_pct:.1f} %; I={i_ka:.3f} kA"
            except Exception as e:
                text = f"Line '{best_line}' - Error while reading results: {e}"
            dpg.set_value(self.hover_text_tag, text)
            return

        # No nearby object
        dpg.set_value(self.hover_text_tag, "-")

    # --------------------------------------------------------------------------------------------------------
    # Internal methods (helpers)
    def _collect_bus_canvas_points(self, zoom: int, tile_size: tuple[int, int]):
        """Determine pixel coordinates of all buses in tile coordinate space."""
        bus_canvas_points: dict[int, tuple[float, float]] = {}
        for idx, row in self.pp_net.bus.iterrows():
            if row.get("geo", None) is None:
                continue
            lon, lat = self._extract_lat_lon(row.get("geo"))[0]

            tile_x, tile_y = Coordinate.from_latlon(lat, lon).tile_xy(zoom, floor_=False)
            bus_canvas_points[idx] = (tile_x * tile_size[0], tile_y * tile_size[1])
            self._map_bus_latlon[idx] = (lat, lon)
        return bus_canvas_points

    def _collect_line_canvas_points(self, zoom: int, tile_size: tuple[int, int]):
        """Determine ordered pixel coordinates of all lines."""
        line_canvas_points: dict[int, list[tuple[float, float]]] = {}
        # Get all line geo data
        for idx, row in self.pp_net.line.iterrows():
            coords = self._extract_lat_lon(row.get("geo"))
            if not coords:
                continue
            
            # Process all coordinates
            canvas_pts = []
            self._map_line_latlon[idx] = []
            for lon, lat in coords:  
                if lat is None or lon is None:
                    continue
                tile_x, tile_y = Coordinate.from_latlon(lat, lon).tile_xy(zoom, floor_=False)
                # Store canvas and lat/lon
                canvas_pts.append((tile_x * tile_size[0], tile_y * tile_size[1]))
                self._map_line_latlon[idx].append((lat, lon))
            
            line_canvas_points[idx] = canvas_pts

        return line_canvas_points

    def _delete_draw_tags(self, tags):
        """Delete DPG tags recursively (single or nested)."""
        for tag in tags:
            if isinstance(tag, (list, tuple)):
                self._delete_draw_tags(tag)
            elif dpg.does_item_exist(tag):
                dpg.delete_item(tag)

    def _tile_pixel_from_latlon(self, lat: float, lon: float, zoom: int, tile_size: tuple[int, int]):
        """Convert geographic coordinates to tile pixel coordinates."""
        coord = Coordinate.from_latlon(lat, lon)
        tile_x, tile_y = coord.tile_xy(zoom, floor_=False)
        return tile_x * tile_size[0], tile_y * tile_size[1]

    def _point_segment_distance(self, px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
        """Compute the shortest distance from a point to a segment."""
        dx = bx - ax
        dy = by - ay
        if dx == 0.0 and dy == 0.0:
            return math.hypot(px - ax, py - ay)
        t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        cx = ax + t * dx
        cy = ay + t * dy
        return math.hypot(px - cx, py - cy)
    
    def _extract_lat_lon(self, geo_raw) -> list[tuple[float, float]]:
        """Extract ``(lon, lat)`` coordinates from Point or LineString GeoJSON."""
        list_lat_lon = []
        # Check if GeoRaw can be processed
        if isinstance(geo_raw, str):
            geo = json.loads(geo_raw)
        elif isinstance(geo_raw, dict):
            geo = geo_raw
        else:
            return list_lat_lon

        # Process depending on coordinate type
        if geo.get("type") == "Point":
            list_lat_lon.append(geo.get("coordinates", [None, None]))
        elif geo.get("type") == "LineString":
            geo_list = geo.get("coordinates")
            for coords in geo_list:
                list_lat_lon.append(coords)

        return list_lat_lon

    def _draw_colorbar(self,
        x0: float, x1: float,       # Horizontal position of the bar
        y0: float, y1: float,       # Vertical position (top/bottom)
        vmin: float, vmax: float,   # Value range of the scale
        title: str,                 # Colorbar title
        segments: int = 100         # Number of color segments (gradient quality)
        ):
        """
        Draw a vertical color bar with scale, ticks, and title.

        The gradient is approximated by many small rectangles.
        """
        # Create list of scale values (labels)
        ticks = list(np.linspace(vmin, vmax, 5))

        # Height offset used to place the title
        y_offset = 50
        
        height = y1 - y0 - y_offset
        seg_h = height / segments

        # Draw gradient (each segment is a rectangle with interpolated color)
        for i in range(segments):
            frac = i / (segments - 1)
            value = vmin + frac * (vmax - vmin)
            color = self._get_color(vmin, vmax, value)

            sy0 = y1 - (i + 1) * seg_h
            sy1 = y1 - i * seg_h
            
            # Draw rectangle for this segment
            tag = dpg.generate_uuid()
            dpg.draw_rectangle(
                pmin=(x0, sy0),
                pmax=(x1, sy1),
                fill=color,
                color=color,
                parent=self.legend_node,
                tag=tag
            )
            self._legend_draw_tags.append(tag)

        # Frame
        tag = dpg.generate_uuid()
        dpg.draw_rectangle(
            pmin=(x0, y0+y_offset),
            pmax=(x1, y1),
            color=(60, 60, 60, 255),
            fill=(0, 0, 0, 0),
            parent=self.legend_node,
            tag=tag
        )
        self._legend_draw_tags.append(tag)

        # Tick marks + labels
        for tick in ticks:
            frac = (tick - vmin) / (vmax - vmin)
            y = y1 - frac * height

            tag = dpg.generate_uuid()
            dpg.draw_line(
                p1=(x1, y),
                p2=(x1 + 6, y),
                color=(40, 40, 40, 255),
                thickness=1,
                parent=self.legend_node,
                tag=tag
            )
            self._legend_draw_tags.append(tag)

            label = f"{tick:.2f}".rstrip("0").rstrip(".") if isinstance(tick, float) else str(tick)

            tag = dpg.generate_uuid()
            dpg.draw_text(
                pos=(x1 + 10, y - 7),
                text=label,
                color=(20, 20, 20, 255),
                parent=self.legend_node,
                tag=tag,
                size=15
            )
            self._legend_draw_tags.append(tag)

        # Title label
        tag = dpg.generate_uuid()
        dpg.draw_text(
            pos=(x0 - 10 , y0 - 10),
            text=title,
            color=(20, 20, 20, 255),
            parent=self.legend_node,
            tag=tag,
            size=15
        )
        self._legend_draw_tags.append(tag)

    def _lerp_color(self, c1, c2, t: float):
        """Linearly interpolate between two RGBA colors."""
        t = max(0.0, min(1.0, t))
        return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(4))