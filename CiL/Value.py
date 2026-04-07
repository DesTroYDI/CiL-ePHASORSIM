# -*- coding: utf-8 -*-
"""
ModbusValue.py
@author: Groß, Hendrik
"""
import numpy as np
import struct
from pymodbus.client import AsyncModbusTcpClient
from dataclasses import dataclass
from .Enum import ModbusDataType, DataType

@dataclass
class PandaPowerValue:
    """Simple data holder for values from the pandapower network model."""
    value: float | bool = np.nan            # Internal value from the pandapower network element
    unit: str | None = None                 # Optional: physical unit of the scaled value (e.g. 'V', 'A', 'kW')
    scale: float = 1.0                      # Optional: scaling factor used to convert the raw value into the physical quantity (default=1.0)

@dataclass
class ModbusValue:
    """
    Representation of a Modbus register including full communication handling.

    This dataclass manages a Modbus register (or multiple registers for 32-bit values) and handles the full communication: reading from the slave and writing to the slave.

    **Functionality:**
        - Supports all common Modbus data types (DIGITAL, INT16, UINT16, INT32, UINT32, FLOAT32)
        - Automatic encoding/decoding between raw values and physical quantities
        - Scaling factors and units for physical interpretation
        - Different Modbus memory areas depending on controllability (RO vs RW)

    **Modbus function codes:**
        - Read-only (RO):
          - DIGITAL: Read Discrete Input (FunctionCode 2)
          - 16/32-bit: Read Input Registers (FunctionCode 4)
        - Read-write (RW):
          - DIGITAL: Read/Write Coil (FunctionCode 1/5)
          - 16/32-bit: Read/Write Holding Registers (FunctionCode 3/6 or 16)

    **IMPORTANT - Byte ordering:**
        The Modbus slave configuration in RT-Lab MUST use 'BACD' byte ordering.
        This corresponds to the IEEE-754 standard for floating point!

    **Attributes:**
        - data_type (DataType): Data type (DIGITAL, INT16, UINT16, INT32, UINT32, FLOAT32)
        - address (int): Modbus address of the register/coil
        - unit (str): Physical unit (e.g. 'V', 'A', 'MW') - optional
        - scale (float): Scaling factor (default value: 1.0)
        - modbus_client (AsyncModbusTcpClient): Reference to the Modbus master
        - value (float | bool): Current (scaled) value
    """
    # Attributes for configuring the Modbus communication addressing
    modbus_data_type: ModbusDataType        # Differentiates the Modbus data type (RW/register or bit)
    data_type: DataType                     # Data type used to encode and decode register values
    address: int                            # Modbus address of the register/coil (the accessible memory area is controlled by the value's controllability)
    unit: str | None= None                  # Optional: physical unit of the scaled value (e.g. 'V', 'A', 'kW')
    scale: float = 1.0                      # Optional: scaling factor used to convert the raw value into the physical quantity (default=1.0)
                 
    # Attributes for active communication
    modbus_client: AsyncModbusTcpClient | None = None   # Modbus master (TCP/IP client)
    value: float | bool = np.nan                        # Scaled value from the Modbus register

    async def read(self) -> float | bool:
        """
        Asynchronous read operation from the configured slave.

        This method automatically selects the correct Modbus function code based on:
        - ModbusDataType (modbus_data_type): determines 1-bit (coil/discrete) or 16/32-bit registers (RO input or RW holding registers)
        - Data type (data_type): determines 16/32-bit registers

        **Modbus function codes:**
            Read-only (ro=False):
                - DIGITAL: Discrete Input (FunctionCode 2)
                - 16-bit: Input Registers (FunctionCode 4)
                - 32-bit: Input Registers x2 (FunctionCode 4)
            Read-write (rw=True):
                - DIGITAL: Coil (FunctionCode 1)
                - 16-bit: Holding Register (FunctionCode 3)
                - 32-bit: Holding Registers x2 (FunctionCode 3)
        
        **Workflow:**
        1. Check whether address, data type, and Modbus data type are specified
        2. Perform the Modbus read operation and determine the number of registers to read
        3. Check for errors (response is None or error flag set)
        4. Decode raw values and scale with self.scale
        5. Store the result in self.value

        :return: The read and scaled value
        :rtype: float | bool
        :raises ConnectionError: If the Modbus request fails or the address is invalid
        :raises ValueError: If the Modbus address was not configured
        :raises TypeError: If the object has no controllability information
        """
        # Address present? otherwise raise an error
        if self.address is None:
            raise ValueError("No Modbus address defined")
        elif self.modbus_client is None:
            raise ValueError("No Modbus client defined")
        
        # Validate the enum values in case imports created incompatible instances
        self.modbus_data_type = ModbusDataType(self.modbus_data_type.value)
        self.data_type = DataType(self.data_type.value)

        response = None
        cmd_str = ""
        # 1-Bit [Discrete Input | COIL]
        if self.modbus_data_type == ModbusDataType.DISCRETE_INPUT:
            # Modbus - Read Discrete Input (FunctionCode 2)
            cmd_str = "Read Discrete Input (FunctionCode 2)"
            response = await self.modbus_client.read_discrete_inputs(
                address=self.address,
                count=1                                 # Read one bit
            )
        elif self.modbus_data_type == ModbusDataType.COIL:
            # Modbus - Read Coil (FunctionCode 1)
            cmd_str = "Read Coil (FunctionCode 1)"
            response = await self.modbus_client.read_coils(
                address=self.address,
                count=1                                 # Read one bit
            )
        elif self.modbus_data_type == ModbusDataType.INPUT_REGISTER:
            # Modbus - Read Input Registers (FunctionCode 4)
            cmd_str = "Read Input Registers (FunctionCode 4)"
            response = await self.modbus_client.read_input_registers(
                address=self.address,
                count=self.data_type.register_count     # The data type contains the number of registers to read
            )
        elif self.modbus_data_type == ModbusDataType.HOLDING_REGISTER:
            # Modbus - Read Holding Registers (FunctionCode 3)
            cmd_str = "Read Holding Registers (FunctionCode 3)"
            response = await self.modbus_client.read_holding_registers(
                address=self.address,
                count=self.data_type.register_count     # The data type contains the number of registers to read
            )
        else:
            raise ValueError(f"ModbusDataType could not be identified: '{str(self.modbus_data_type)}'")

        # Check the Modbus request
        if response is None or response.isError():
            raise ConnectionError(f"!!! Error - Address could not be read [{self.address}] | {cmd_str}")
    
        # Convert the received data for application use
        if self.modbus_data_type.is_bit_type:
            self.value = bool(response.bits[0])
        else:
            # Decode the registers (for FLOAT32, two registers must be read, etc.)           
            _value = self.__decode(response.registers)
            # Apply scaling
            self.value = _value * self.scale         
        return self.value
    
    async def write(self) -> float | bool:
        """
        Writes the current value asynchronously to the Modbus slave.

        The method scales the value back to raw format, encodes it into the
        register format, and uses the appropriate write function code.

        :return: The written (scaled) value
        :rtype: float | bool
        :raises ConnectionError: If the Modbus write operation fails
        :raises ValueError: If the Modbus address or value was not configured
        """
        if self.address is None:
            raise ValueError("No Modbus address defined")
        elif self.value is None:
            raise ValueError("No value available to write to Modbus")
        elif self.modbus_client is None:
            raise ValueError("No Modbus client defined")
        
        # Validate the enum values in case imports created incompatible instances
        self.modbus_data_type = ModbusDataType(self.modbus_data_type.value)
        self.data_type = DataType(self.data_type.value)

        cmd_str = ""
        response = None
        # Register
        if not self.modbus_data_type.is_bit_type:
            # Apply scaling
            _value = self.value / self.scale
            # Encode the value and write it to the Modbus slave
            registers = self.__encode(_value)
            # Write Holding Register (one or more registers)
            if self.data_type.register_count == 1:
                # Modbus - Write Holding Register (FunctionCode 6)
                cmd_str = "Write Holding Register (FunctionCode 6)"
                response = await self.modbus_client.write_register(
                    address=self.address,
                    value=registers[0]
                )
            elif self.data_type.register_count > 1:
                # Modbus - Write Holding Registers (FunctionCode 16)
                cmd_str = "Write Holding Registers (FunctionCode 16)"
                response = await self.modbus_client.write_registers(
                    address=self.address,
                    values=registers
                )
            else:
                raise ValueError(f"ModbusDataType or data type could not be identified: '{str(self.modbus_data_type)}'/'{str(self.data_type)}'")
        elif self.modbus_data_type == ModbusDataType.COIL:
            # Modbus - Write Coil (FunctionCode 5)
            cmd_str = "Write Coil (FunctionCode 5)"
            response = await self.modbus_client.write_coil(
                address=self.address,
                value=bool(self.value)
            )
        else:
            raise ValueError(f"ModbusDataType or data type could not be identified: '{str(self.modbus_data_type)}'/'{str(self.data_type)}'")
        
        # Check the Modbus response
        if response is None or response.isError():
            raise ConnectionError(f"!!! Error - Address could not be written [{self.address}] | {cmd_str}")

        return self.value

    # --------------------------------------------------------------------------------------------------------
    # Interne Methoden
    def __decode(self, registers: list[int]) -> float:
        """
        Decodes a list of 16-bit Modbus registers into a numeric value.

        This method converts the raw values from the Modbus slave into Python-native data types:
        - UINT16: Direct conversion
        - INT16: Signed 16-bit integer
        - UINT32/INT32: Combine two registers (high word, low word)
        - FLOAT32: IEEE-754 single precision (two registers)

        **Byte ordering important:** The OPAL-RT 4510 configuration MUST use 'BACD'!
        This corresponds to the IEEE-754 standard floating-point format.

        **Register layout (32-bit example):**
            registers[0] = high word (bits 31-16)
            registers[1] = low word (bits 15-0)

        :param registers: List of 16-bit register values from the slave
                          - 1 element for 16-bit types (INT16, UINT16)
                          - 2 elements for 32-bit types (INT32, UINT32, FLOAT32)
        :type registers: list[int]
        :return: Decoded numeric value as float
        :rtype: float
        :raises ValueError: If data_type is not supported
        """
        # https://docs.python.org/3/library/struct.html
        # UNSIGNED 16-BIT INTEGER (0 bis 65535)
        if self.data_type == DataType.UINT16:
            # Simple conversion because the register is already interpreted as unsigned
            return float(registers[0])

        # SIGNED 16-BIT INTEGER (-32768 bis 32767)
        if self.data_type == DataType.INT16:
            return float(struct.unpack(">h", struct.pack(">H", registers[0]))[0])

        # UNSIGNED 32-BIT INTEGER (0 bis 4.294.967.295)
        if self.data_type == DataType.UINT32:
            raw = (registers[0] << 16) | registers[1]
            return float(raw)

        # SIGNED 32-BIT INTEGER (-2.147.483.648 bis 2.147.483.647)
        if self.data_type == DataType.INT32:
            raw = (registers[0] << 16) | registers[1]
            return float(struct.unpack(">i", struct.pack(">I", raw))[0])

        # IEEE-754 32-BIT FLOATING POINT (single precision)
        if self.data_type == DataType.FLOAT32:
            raw = (registers[1] << 16) | registers[0]
            return struct.unpack("<f", struct.pack("<I", raw))[0]

        raise ValueError("Data type is not supported")

    def __encode(self, value: float) -> list[int]:
        """
        Encodes a numeric value into a list of 16-bit Modbus registers.

        This method is the inverse of __decode(). It converts Python values into the
        Modbus register format for the slave:
        - UINT16: Direct conversion to 16-bit unsigned
        - INT16: Signed 16-bit integer (with sign extension)
        - UINT32/INT32: Split into high word and low word
        - FLOAT32: IEEE-754 single precision (two registers)

        **Byte ordering important:** MUST match __decode() - BACD format!

        **Register layout (32-bit example):**
            result[0] = high word (bits 31-16)
            result[1] = low word (bits 15-0)

        :param value: Value to encode (interpreted as integer or float depending on data_type)
        :type value: float
        :return: List of 16-bit unsigned integers for the Modbus slave
                 - 1 element for 16-bit types
                 - 2 elements for 32-bit types (high word first)
        :rtype: list[int]
        :raises ValueError: If data_type is not supported
        """
        # UNSIGNED 16-BIT INTEGER (0 bis 65535)
        if self.data_type == DataType.UINT16:
            return [int(value)]

        # SIGNED 16-BIT INTEGER (-32768 bis 32767)
        if self.data_type == DataType.INT16:
            return [struct.unpack(">H", struct.pack(">h", int(value)))[0]]

        # UNSIGNED 32-BIT INTEGER (0 bis 4.294.967.295)
        if self.data_type == DataType.UINT32:
            v = int(value)
            return [(v >> 16) & 0xFFFF, v & 0xFFFF]

        # SIGNED 32-BIT INTEGER (-2.147.483.648 bis 2.147.483.647)
        if self.data_type == DataType.INT32:
            raw = struct.unpack(">I", struct.pack(">i", int(value)))[0]
            return [(raw >> 16) & 0xFFFF, raw & 0xFFFF]

        # IEEE-754 32-BIT FLOATING POINT (single precision)
        if self.data_type == DataType.FLOAT32:
            raw = struct.unpack("<I", struct.pack("<f", value))[0]
            return [raw & 0xFFFF, (raw >> 16) & 0xFFFF]

        raise ValueError("Data type is not supported")

    def __repr__(self):
        """Creates a compact string representation for debug output.

        :return: Value with optional unit
        :rtype: str
        """
        _unit = ""
        _value = 0
        # Data consistency checks
        if self.unit is not None:
            _unit = self.unit
        if self.value is not None:
            _value = self.value
        
        return f"{_value:.3f} {_unit}"