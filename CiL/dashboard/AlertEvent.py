# -*- coding: utf-8 -*-
"""
AlertEvent.py
========

@author: Groß, Hendrik
"""
import time
from dataclasses import dataclass
import dearpygui.dearpygui as dpg
from enum import Enum

"""AlertType indicating whether a condition was broken "bad" (False to True) or healed "good" (True to False)."""
class AlertType(Enum):
    """Classifies events as a break or healing of a condition."""
    BROKE = "bad"
    HEALED = "good"

@dataclass()
class AlertEvent:
    """
    Entry in the control room message log.

    An ``AlertEvent`` contains the timestamp, source component, message text, and
    event type for display in the GUI.
    """
    timestamp: float
    element_class: str
    element_name: str
    message: str
    type: AlertType
    time_is_relative: bool = False
    
    def build_dpg_row(self,_start_timestamp:float, parent_tag: int, before_tag: int |None = None) -> int | str:
        """
        Renders the event entry as a DearPyGui row.

        Row format:  [HH:MM:SS.mmm]  Class · Name  -  Message text

        :param _start_timestamp: Start time for relative time display (0 or None for absolute)
        :type _start_timestamp: float
        :param parent_tag: DPG tag of the parent container (e.g. a ``child_window`` in the message panel).
        :type parent_tag: int
        :param before_tag: Optional DPG tag of an already existing child. The new row is inserted *before* this element,
                   so the newest entries appear at the top. ``None`` -> append to the end.
        :type before_tag: int | None
        :return: Tag of the created DPG group
        :rtype: int | str
        """
        # Update the timestamp if a start time was provided
        if _start_timestamp is not None and _start_timestamp != 0:
            self.time_is_relative = True 
            self.timestamp = (self.timestamp - _start_timestamp)

        # Parameter der DPG-Gruppierung
        group_uuid = dpg.generate_uuid()
        row_kwargs = dict(horizontal=True, parent=parent_tag, tag=group_uuid)
        if before_tag is not None:
            row_kwargs["before"] = before_tag

        # Color styling depends on the alert type
        if self.type == AlertType.BROKE:
            row_color = (255, 0, 0)
        elif self.type == AlertType.HEALED:
            row_color = (0, 255, 0)

        with dpg.group(**row_kwargs): # pyright: ignore[reportArgumentType]
            with dpg.drawlist(width=10, height=10):
                dpg.draw_circle((5, 5), 5, color=row_color, fill=row_color) # pyright: ignore[reportPossiblyUnboundVariable]
            dpg.add_text(f"[{self.timestamp_str()}]  {self.element_class} · {self.element_name}  -  {self.message}")
        
        return group_uuid
 
    def timestamp_str(self) -> str:
        """Formats the timestamp as a string (absolute or relative)."""
        if not self.time_is_relative:
            t  = time.localtime(self.timestamp)
            ms = int((self.timestamp % 1) * 1000)
            return f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}.{ms:03d}"
        else:
            hours = int(self.timestamp // 3600)
            minutes = int((self.timestamp % 3600) // 60)
            seconds = int(self.timestamp % 60)
            ms = int((self.timestamp % 1) * 1000)
            
            if hours > 0:
                return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}"
            else:
                return f"{minutes:02d}:{seconds:02d}.{ms:03d}"


    def __str__(self) -> str:
        """Returns a compact, human-readable representation."""
        return (f"[{self.timestamp_str()}] {self.element_class} '{self.element_name}' - {self.message}")