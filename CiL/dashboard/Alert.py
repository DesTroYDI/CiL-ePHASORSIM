# -*- coding: utf-8 -*-
"""
Alert.py
========
Alert system for the CHIL dashboard.
This module contains an abstract base class (``Alert``) and several concrete alert types for typical network events.

Each alert is bound to an ``IModbusElement`` and is evaluated cyclically via
``evaluate()``.

@author: Groß, Hendrik
"""
import time
from abc import ABC, abstractmethod
from .AlertEvent import AlertEvent, AlertType

from ..IModbusElement import IModbusElement

# ─────────────────────────────────────────────────────────────────────────────
# Abstract base class
# ─────────────────────────────────────────────────────────────────────────────

class Alert(ABC):
    """
    Abstract base class for all dashboard alerts.

    An ``Alert`` instance monitors exactly one ``IModbusElement``. The dashboard
    calls ``evaluate()`` once per cycle. When the state changes, an
    ``AlertEvent`` is created.

    Subclasses **must** implement:
        * ``evaluate() -> bool``: Validation logic, ``True`` when the alert is active
        * ``message() -> str``: Display text (optionally dynamic)
    """

    # Constructor
    def __init__(self, element: IModbusElement, label: str | None = None):
        """
        :param element: The ``IModbusElement`` to monitor
        :type element: IModbusElement
        :param label: Optional display name; if ``None`` is passed, ``element.name`` is used
        :type label: str | None
        """
        if not isinstance(element, IModbusElement):
            raise TypeError(f"'element' must be a IModbusElement-Instanz. Recieved: {type(element).__name__}")
        self.element: IModbusElement = element
        self.label: str = label if label else element.name
        self._was_active: bool = False  # State from the previous cycle

    # --------------------------------------------------------------------------------------------------------
    # Abstract methods
    @abstractmethod
    def message(self, _type: AlertType) -> str:
        """Returns the alert text to display for the given event type."""
        raise NotImplementedError

    @abstractmethod
    def evaluate(self) -> bool:
        """
        Runs the validation logic.

        :return: ``True`` if the alert is active, otherwise ``False``.
        :rtype: bool
        """
        raise NotImplementedError

    # --------------------------------------------------------------------------------------------------------
    # Public methods
    def check_and_update(self) -> AlertEvent | None:
        """
        Evaluates the alert and creates an event when the state changes.

        :return: ``AlertEvent`` on an edge transition, otherwise ``None``
        :rtype: AlertEvent | None
        """
        # Evaluate the condition
        _active = self.evaluate()

        # If the state changed after the cycle, create an event
        _event_type = None
        if _active and not self._was_active:
            # Condition was violated
            _event_type = AlertType.BROKE
        elif not _active and self._was_active:
            # Condition is no longer violated
            _event_type = AlertType.HEALED

        # Store the current state for the next cycle
        self._was_active = _active

        if _event_type is None:
            return None
        else:
            return AlertEvent(
                timestamp=time.time(),
                element_class=type(self.element).__name__,
                element_name=self.label,
                message=self.message(_event_type),
                type=_event_type
            )

class AlertOnAttribute(Alert):
    """Base class for alerts that monitor a specific attribute value."""

     # Constructor
    def __init__(self, element: IModbusElement, attribute_key: str | None = None, name: str | None = None):
        """
        :param element: The ``IModbusElement`` to monitor
        :type element: IModbusElement
        :param attribute_key: Key in ``element.values`` whose value is monitored
        :type attribute_key: str | None
        :param name: Optional display name
        :type name: str | None
        """
        super().__init__(element, name)

        # Check whether an attribute for the value was provided
        if attribute_key is None:
            raise ValueError("No 'attribute_key' provided!")
        elif attribute_key not in self.element.values:
            raise ValueError(f"Invalid 'attribute_key' provided! '{attribute_key}' not found in element.values. Available keys: {list(self.element.values.keys())}")
        
        self.attribute_key = attribute_key
        self._previous_value: float | bool | None = None

    def get_value(self) -> float | None:
        """Returns the currently monitored value from ``element.values`` or ``element.value``."""
        value = None
        if self.attribute_key is None:
            value = self.element.value
        # Key is invalid
        elif not self.attribute_key in self.element.values:
            value = self.element.value
        else:
            value = self.element.values[self.attribute_key].value
        
        self.value = value
        return value
    
    def get_unit(self) -> str:
        """Returns the unit of the monitored value including a leading space."""
        # Unit from the value or fallback value
        unit = ""
        if self.attribute_key is None:
            tmp_unit = self.element.unit
        else:
            tmp_unit = self.element.values[self.attribute_key].unit
        # Check whether the unit is empty and avoid double spaces
        if tmp_unit != "":
            unit = f" {tmp_unit}"
        
        self.unit = unit
        return unit
     
# --------------------------------------------------------------------------------------------------------
# Concrete alert classes
class VoltageBandAlert(Alert):
    """Alert for monitoring a voltage band in per-unit."""
    # Constructor
    def __init__(self, element: IModbusElement, v_min_pu: float | None = None, v_max_pu: float | None = None, name: str | None = None):
        super().__init__(element, name)
        self.v_min_pu = v_min_pu
        self.v_max_pu = v_max_pu

        # No voltage band limit specified
        if v_min_pu is None and v_max_pu is None:
            raise ValueError("VOLTAGEBANDALTER - No voltage limits specified! At least one of 'v_min_pu' or 'v_max_pu' must be provided.")

    # --------------------------------------------------------------------------------------------------------
    # Public properties 
    @property
    def _current_vm_pu(self) -> float | None:
        """Returns the current voltage magnitude in per-unit, otherwise ``None``."""
        u = getattr(self.element, "voltage_complex", None)
        if u is None:
            return None
        # The bus stores voltage_complex either in kV or p.u.
        base = getattr(self.element, "base_voltage", -1)
        if base and base > 0:
            return abs(u) / base    
        return abs(u)               

    def message(self, _type: AlertType) -> str:
        """Creates the alert text for overvoltage, undervoltage, or recovery."""
        # First check whether a voltage value can be read at all
        vm = self._current_vm_pu
        if vm is None:
            return "No voltage value available!"
        
        # Form the message
        message = ""
        # Voltage band is back within limits
        if _type == AlertType.HEALED:
            message = f"Voltage back to normal: {vm:.4f} p.u."
        # Condition violated and determine whether it is overvoltage or undervoltage
        elif _type == AlertType.BROKE:
            if self.v_min_pu is not None and vm < self.v_min_pu:
                message = f"Undervoltage {vm:.4f} p.u. < {self.v_min_pu:.4f} p.u."
            elif self.v_max_pu is not None and vm > self.v_max_pu:
                message = f"Overvoltage {vm:.4f} p.u. > {self.v_max_pu:.4f} p.u."
        else:
            message="Error: No alert type detected!" 

        return message

    # --------------------------------------------------------------------------------------------------------
    # Validation logic 
    def evaluate(self) -> bool:
        """Checks whether the current voltage is outside the configured band."""
        vm = self._current_vm_pu
        if vm is None:
            return False
        below = self.v_min_pu is not None and vm < self.v_min_pu
        above = self.v_max_pu is not None and vm > self.v_max_pu
        return below or above

class LimitAlert(AlertOnAttribute):
    """Alert when an upper limit is exceeded."""
    # Constructor
    def __init__(self, element: IModbusElement, attribute_key: str | None = None, name: str | None = None, limit: float = 1):
        """
        :param attribute_key: Key of the value to monitor in ``element.values``; if ``None``, ``element.value`` is used
        :type attribute_key: str | None
        """
        super().__init__(element,attribute_key, name)
        self.limit = float(limit)

        # Determine the unit label
        self.get_unit()

    # --------------------------------------------------------------------------------------------------------
    # Public properties 
    def message(self, _type: AlertType) -> str:
        """Creates the alert text for a limit violation or recovery."""        
        # Form the message
        message = ""
        if _type == AlertType.HEALED:
            message = f"Threshold compliance: '{self.element.name}' = {self.value:.3f}{self.unit} <= {self.limit:.3f}{self.unit}"
        elif _type == AlertType.BROKE:
            return f"Threshold exceedance: '{self.element.name}' = {self.value:.3f}{self.unit} > {self.limit:.3f}{self.unit}"
        else: 
            "Error: No alert type detected!" 

        return message

    # --------------------------------------------------------------------------------------------------------
    # Validation logic
    def evaluate(self) -> bool:
        """Checks whether the configured attribute exceeds the upper limit."""
        value = self.get_value()
        # Check whether the limit has been exceeded
        if value is None:
            return False
        return value > self.limit

class ValueChangedAlert(AlertOnAttribute):
    """Alert for value changes with optional threshold logic."""

     # Constructor
    def __init__(self, element: IModbusElement, attribute_key: str | None = None, name: str | None = None, threshold: float = 0.1):
        """
        :param element: The ``IModbusElement`` to monitor
        :type element: IModbusElement
        :param threshold: Minimum change that triggers an alert
        :type threshold: float
        :param attribute_key: Key of the value to monitor
        :type attribute_key: str | None
        """
        super().__init__(element,attribute_key, name)
        self.threshold = threshold

        # Determine the unit label
        self.get_unit()

    # --------------------------------------------------------------------------------------------------------
    # Public properties 
    def message(self, _type: AlertType) -> str:
        """Creates the alert text for a detected value change."""
        # Form the message
        name_val = "Change of state value"
        if self.attribute_key is not None:
            name_val = f"Change of state value ['{self.attribute_key}']"

        # Output the state change
        message = ""
        if isinstance(self.value, bool):
            message = f"{name_val}: {self.value}"
        else:
            message = f"{name_val} [Threshold={self.threshold:.3}{self.unit}]: {self.value:.3}{self.unit}"
        return message

    # --------------------------------------------------------------------------------------------------------
    # Validation logic
    def evaluate(self) -> bool:
        """Checks whether the value changed by more than ``threshold``."""
        # Get the initial object value
        if self._previous_value is None:
            self._previous_value = self.get_value()
            return False
        
        current_value = self.get_value()
        if current_value is None:
            return False
        # Check whether a difference greater than the threshold occurred
        if abs(current_value - self._previous_value) > self.threshold:
            self._previous_value = current_value
            return True
        else:
            return False

class ControllableSignalAlert(AlertOnAttribute):
    """
    Alert for changes to a discrete or continuous control signal.

    Typical use cases are switching disconnect elements or turning loads and generators
    on and off.
    """

    # --------------------------------------------------------------------------------------------------------
    # Public properties 
    def message(self, _type: AlertType) -> str:
        """Creates the alert text for a signal change or return to normal state."""
        # Form the message
        message = ""
        
        signal_name =f"'{self.attribute_key}' = " if self.attribute_key is not None else ""
        if _type == AlertType.HEALED:
            message = f"Control signal revoked: {signal_name}{self.value}"
        else:
            message = f"Control signal: {signal_name}{self.value}"
        return message

    # --------------------------------------------------------------------------------------------------------
    # Validation logic
    def evaluate(self) -> bool:
        """Checks whether the monitored signal value changed since the last cycle."""
        # Get the initial object value
        if self._previous_value is None:
            self._previous_value = self.get_value()
            return False

        # Check whether the control signal state value changed
        current_value = self.get_value()
        if current_value is None:
            return False
        if current_value != self._previous_value:
            self._previous_value = current_value
            return True
        return False

class ControllableLimitAlert(AlertOnAttribute):
    """
    Alert for a power limit against an available generation/load profile value.

    The alert is active when the controlled value is greater than the theoretically available value or when a change occurs.
    """

    def __init__(self, element: IModbusElement, attribute_key: str | None = None, name: str | None = None, profile_attribute_key: str | None = None):
        """
        :param element: The ``IModbusElement`` to monitor
        :type element: IModbusElement
        :param name: Optional display name
        :type name: str | None
        :param attribute_key: If set, ``element.values[attribute_key]`` is used. Otherwise ``element.value`` is used for the comparison
        :type attribute_key: str | None
        :param profile_attribute_key: If set, ``element.values[profile_attribute_key]`` is used. Serves as the theoretical or available comparison value
        :type profile_attribute_key: str | None
        """
        super().__init__(element, attribute_key, name)

        # Check whether an attribute for the theoretical value was provided
        if profile_attribute_key is None:
            raise ValueError("No 'profile_attribute_key' specified")
        elif profile_attribute_key not in self.element.values:
            raise ValueError(f"No 'profile_attribute_key' found in element '{self.element}'")
        self.profile_attribute_key = profile_attribute_key

        # Determine the unit label
        self.get_unit()

    # --------------------------------------------------------------------------------------------------------
    # Public properties 
    def message(self, _type: AlertType) -> str:
        # First check whether a value can be read
        """Creates the alert text for a signal change or profile limit violation."""
        # Form the message
        message = ""
        signal_name =f"'{self.attribute_key}' = " if self.attribute_key is not None else ""

        # First check whether the control signal changed
        if self.value != self._previous_value:
            self._previous_value = self.value
            message = f"Changed control signal: {signal_name}{self.value}{self.unit}"
        # If the profile value falls below the control value
        elif _type == AlertType.HEALED:
            message = f"Control ineffective: {signal_name}{self.profile_value:.3f}{self.unit} <= {self.value:.3f}{self.unit}"
        # Control active again after recovery
        else:
            message = f"Control limit exceeded: {signal_name}{self.profile_value:.3f}{self.unit} <= {self.value:.3f}{self.unit}"
        
        return message

    # --------------------------------------------------------------------------------------------------------
    # Validation logic
    def evaluate(self) -> bool:
        """Checks signal changes and active limitation against the profile value."""
        # Get the initial object value
        if self._previous_value is None:
            self._previous_value = self.get_value()
            return False
        
        # Get values
        current_value = self.get_value()
        if current_value is None:
            return False
        self.profile_value = self.element.values[self.profile_attribute_key].value
        # Run the check
        if current_value != self._previous_value:
            return True
        else:
            return current_value < self.profile_value
