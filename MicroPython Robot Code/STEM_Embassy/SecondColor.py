"""
TCS34725 Color Sensor Driver for MicroPython
Based on Adafruit's TCS34725 driver
"""

import time
import ustruct
from machine import Pin, I2C

# TCS34725 Command Register
_COMMAND_BIT = const(0x80)

# TCS34725 Registers
_REGISTER_ENABLE = const(0x00)
_REGISTER_ATIME = const(0x01)
_REGISTER_WTIME = const(0x03)
_REGISTER_AILT = const(0x04)
_REGISTER_AIHT = const(0x06)
_REGISTER_APERS = const(0x0C)
_REGISTER_CONFIG = const(0x0D)
_REGISTER_CONTROL = const(0x0F)
_REGISTER_ID = const(0x12)
_REGISTER_STATUS = const(0x13)
_REGISTER_CDATAL = const(0x14)  # Clear channel data
_REGISTER_RDATAL = const(0x16)  # Red channel data
_REGISTER_GDATAL = const(0x18)  # Green channel data
_REGISTER_BDATAL = const(0x1A)  # Blue channel data

# Enable Register Bits
_ENABLE_AIEN = const(0x10)   # RGBC Interrupt Enable
_ENABLE_WEN = const(0x08)    # Wait enable
_ENABLE_AEN = const(0x02)    # RGBC Enable
_ENABLE_PON = const(0x01)    # Power on

# Status Register Bits
_AVALID = const(0x01)        # RGBC data is valid

# Integration time settings (ms)
_INTEGRATION_TIME_2_4MS = const(0xFF)   # 2.4ms - 1 cycle
_INTEGRATION_TIME_24MS = const(0xF6)    # 24ms  - 10 cycles
_INTEGRATION_TIME_101MS = const(0xD5)   # 101ms - 42 cycles
_INTEGRATION_TIME_154MS = const(0xC0)   # 154ms - 64 cycles
_INTEGRATION_TIME_700MS = const(0x00)   # 700ms - 256 cycles

# Gain settings
_GAIN_1X = const(0x00)
_GAIN_4X = const(0x01)
_GAIN_16X = const(0x02)
_GAIN_60X = const(0x03)

_GAINS = (1, 4, 16, 60)
_CYCLES = (0, 1, 2, 3, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60)


class TCS34725:
    """Driver for the TCS34725 color sensor."""
    
    def __init__(self, i2c=None, address=0x29):
        """Initialize the TCS34725 sensor.
        
        Args:
            i2c: I2C bus instance. If None, default pins will be used.
            address: I2C address of the sensor (default 0x29)
        """
        if i2c is None:
            self.i2c = I2C(0, scl=Pin(21), sda=Pin(20), freq=400000)
        else:
            self.i2c = i2c
            
        self.address = address
        self._active = False
        
        # Check sensor ID
        sensor_id = self.sensor_id()
        if sensor_id not in (0x44, 0x10):
            raise RuntimeError(f"Wrong sensor ID: 0x{sensor_id:02x}")
        
        # Initialize sensor with default settings
        self.set_integration_time(24)
        self.set_gain(4)
        self.active(True)

    def _write_register(self, register, value):
        """Write a byte to the specified register."""
        self.i2c.writeto_mem(self.address, register | _COMMAND_BIT, bytes([value]))

    def _read_register(self, register):
        """Read a byte from the specified register."""
        return self.i2c.readfrom_mem(self.address, register | _COMMAND_BIT, 1)[0]

    def _read_word(self, register):
        """Read a 16-bit word from the specified register."""
        data = self.i2c.readfrom_mem(self.address, register | _COMMAND_BIT, 2)
        return ustruct.unpack('<H', data)[0]

    def active(self, state=None):
        """Activate or deactivate the sensor.
        
        Args:
            state: True to activate, False to deactivate, None to get current state
            
        Returns:
            Current active state if state is None
        """
        if state is None:
            return self._active
        
        enable = self._read_register(_REGISTER_ENABLE)
        
        if state:
            self._write_register(_REGISTER_ENABLE, enable | _ENABLE_PON)
            time.sleep_ms(3)
            self._write_register(_REGISTER_ENABLE, enable | _ENABLE_PON | _ENABLE_AEN)
            self._active = True
        else:
            self._write_register(_REGISTER_ENABLE, enable & ~(_ENABLE_PON | _ENABLE_AEN))
            self._active = False

    def sensor_id(self):
        """Read the sensor ID."""
        return self._read_register(_REGISTER_ID)

    def set_integration_time(self, value_ms):
        """Set integration time in milliseconds.
        
        Args:
            value_ms: Integration time in milliseconds (2.4-700)
        """
        if value_ms <= 2.4:
            atime = _INTEGRATION_TIME_2_4MS
            self._integration_time = 2.4
        elif value_ms <= 24:
            atime = _INTEGRATION_TIME_24MS
            self._integration_time = 24
        elif value_ms <= 101:
            atime = _INTEGRATION_TIME_101MS
            self._integration_time = 101
        elif value_ms <= 154:
            atime = _INTEGRATION_TIME_154MS
            self._integration_time = 154
        else:
            atime = _INTEGRATION_TIME_700MS
            self._integration_time = 700
            
        self._write_register(_REGISTER_ATIME, atime)

    def set_gain(self, gain):
        """Set sensor gain.
        
        Args:
            gain: 1, 4, 16, or 60
        """
        if gain not in _GAINS:
            raise ValueError("Gain must be 1, 4, 16, or 60")
        
        control = _GAINS.index(gain)
        self._write_register(_REGISTER_CONTROL, control)
        self._gain = gain

    def _data_ready(self):
        """Check if RGBC data is ready."""
        status = self._read_register(_REGISTER_STATUS)
        return bool(status & _AVALID)

    def read_rgbc(self):
        """Read red, green, blue, and clear data.
        
        Returns:
            Tuple of (red, green, blue, clear) values
        """
        if not self._active:
            self.active(True)
        
        # Wait for data to be ready
        while not self._data_ready():
            time.sleep_ms(int(self._integration_time) + 1)
        
        clear = self._read_word(_REGISTER_CDATAL)
        red = self._read_word(_REGISTER_RDATAL)
        green = self._read_word(_REGISTER_GDATAL)
        blue = self._read_word(_REGISTER_BDATAL)
        
        return red, green, blue, clear

    def read_color_temperature(self):
        """Calculate color temperature and lux from RGBC data.
        
        Returns:
            Tuple of (color_temperature, lux)
        """
        r, g, b, c = self.read_rgbc()
        
        if c == 0:
            return 0, 0
        
        # Calculate XYZ
        x = -0.14282 * r + 1.54924 * g + -0.95641 * b
        y = -0.32466 * r + 1.57837 * g + -0.73191 * b
        z = -0.68202 * r + 0.77073 * g + 0.56332 * b
        
        # Calculate chromaticity coordinates
        xc = x / (x + y + z)
        yc = y / (x + y + z)
        
        # Calculate CCT (Correlated Color Temperature)
        n = (xc - 0.3320) / (0.1858 - yc)
        cct = 449.0 * n**3 + 3525.0 * n**2 + 6823.3 * n + 5520.33
        
        # Lux calculation
        lux = y / (self._integration_time * self._gain / 24.0)
        
        return cct, lux

    def read_rgb_normalized(self):
        """Read RGB values normalized to 0-255 range.
        
        Returns:
            Tuple of (red, green, blue) values in 0-255 range
        """
        r, g, b, c = self.read_rgbc()
        
        if c == 0:
            return 0, 0, 0
        
        red = int((r / c) * 255)
        green = int((g / c) * 255)
        blue = int((b / c) * 255)
        
        return red, green, blue

    def read_rgb_hex(self):
        """Read RGB color as hex string.
        
        Returns:
            Hex color string (e.g. "FF0000" for red)
        """
        r, g, b = self.read_rgb_normalized()
        return f"{r:02x}{g:02x}{b:02x}"

    def set_interrupt(self, enabled=True, persistence=0):
        """Enable or disable interrupt.
        
        Args:
            enabled: True to enable, False to disable
            persistence: Number of consecutive values needed to trigger interrupt
        """
        enable = self._read_register(_REGISTER_ENABLE)
        
        if enabled:
            if persistence not in _CYCLES:
                raise ValueError("Invalid persistence value")
            
            self._write_register(_REGISTER_ENABLE, enable | _ENABLE_AIEN)
            self._write_register(_REGISTER_APERS, _CYCLES.index(persistence))
        else:
            self._write_register(_REGISTER_ENABLE, enable & ~_ENABLE_AIEN)

    def set_interrupt_limits(self, low=0, high=0xFFFF):
        """Set interrupt thresholds.
        
        Args:
            low: Low threshold (16-bit)
            high: High threshold (16-bit)
        """
        self.i2c.writeto_mem(self.address, _REGISTER_AILT | _COMMAND_BIT, ustruct.pack('<H', low))
        self.i2c.writeto_mem(self.address, _REGISTER_AIHT | _COMMAND_BIT, ustruct.pack('<H', high))

    def clear_interrupt(self):
        """Clear interrupt flag."""
        self.i2c.writeto(self.address, b'\xE6')

    def __del__(self):
        """Cleanup when object is deleted."""
        self.active(False)


# Example usage:
if __name__ == "__main__":
    # Initialize the sensor
    sensor = TCS34725()
    
    # Set integration time to 24ms and gain to 4x
    sensor.set_integration_time(24)
    sensor.set_gain(4)
    
    while True:
        # Read RGB values
        r, g, b, c = sensor.read_rgbc()
        print(f"Red: {r}, Green: {g}, Blue: {b}, Clear: {c}")
        
        # Read color temperature and lux
        temp, lux = sensor.read_color_temperature()
        print(f"Color Temp: {temp:.0f}K, Lux: {lux:.2f}")
        
        # Read normalized RGB values
        r_norm, g_norm, b_norm = sensor.read_rgb_normalized()
        print(f"RGB (0-255): {r_norm}, {g_norm}, {b_norm}")
        
        # Read hex color
        hex_color = sensor.read_rgb_hex()
        print(f"Hex color: #{hex_color}")
        
        print("-" * 30)
        time.sleep(1)