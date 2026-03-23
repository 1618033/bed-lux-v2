#-------------------------------------------------------------------------------
# qwiic_veml.py
#
# Python library for the the following SparkFun sensors:
# 1) [SparkFun Qwiic VEML6030 Ambient Light Sensor](https://www.sparkfun.com/products/15436)
# 2) [SparkFun Qwiic VEML7700 Ambient Light Sensor](https://www.sparkfun.com/products/29211)
#-------------------------------------------------------------------------------
# Written by SparkFun Electronics, November 2023
#
# This Python library supports the SparkFun Electroncis Qwiic
#
# More information on qwiic is at https://www.sparkfun.com/qwiic
#
# Do you like this library? Help support SparkFun. Buy a board!
#===============================================================================
# Copyright (c) 2023 SparkFun Electronics
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#===============================================================================
# This code was generated in part with ChatGPT (created by OpenAI). The code was
# reviewed and edited by the following human(s):
#
# Dryw Wade
#===============================================================================

"""!
qwiic_veml
============
Python module for the following sensors:
1) [SparkFun Qwiic VEML6030 Ambient Light Sensor](https://www.sparkfun.com/products/15436)
2) [SparkFun Qwiic VEML7700 Ambient Light Sensor](https://www.sparkfun.com/products/29211)
This is a port of the existing [Arduino Library](https://github.com/sparkfun/SparkFun_Ambient_Light_Sensor_Arduino_Library)
This package can be used in conjunction with the overall [SparkFun Qwiic Python Package](https://github.com/sparkfun/Qwiic_Py)
New to Qwiic? Take a look at the entire [SparkFun Qwiic ecosystem](https://www.sparkfun.com/qwiic).
"""

from micropython_i2c import MicroPythonI2C
import time

# Define the device name and I2C addresses. These are set in the class defintion
# as class variables, making them avilable without having to create a class
# instance. This allows higher level logic to rapidly create a index of Qwiic
# devices at runtine
_DEFAULT_NAME = "Qwiic VEML"

# Some devices have multiple available addresses - this is a list of these
# addresses. NOTE: The first address in this list is considered the default I2C
# address for the device.
_AVAILABLE_I2C_ADDRESS = [0x48, 0x10]

# Define the class that encapsulates the device being created. All information
# associated with this device is encapsulated by this class. The device class
# should be the only value exported from this module.
class VEML7700(object):
    # Set default name and I2C address(es)
    device_name         = _DEFAULT_NAME
    available_addresses = _AVAILABLE_I2C_ADDRESS

    # Constants
    VEML_ENABLE = 0x01
    VEML_DISABLE = 0x00
    VEML_SHUTDOWN = 0x01
    VEML_POWER = 0x00
    VEML_NO_INT = 0x00
    VEML_INT_HIGH = 0x01
    VEML_INT_LOW = 0x02
    VEML_UNKNOWN_ERROR = 0xFF

    # 16-bit registers
    VEML_SETTING_REG = 0x00
    VEML_H_THRESH_REG = 0x01
    VEML_L_THRESH_REG = 0x02
    VEML_POWER_SAVE_REG = 0x03
    VEML_AMBIENT_LIGHT_DATA_REG = 0x04
    VEML_WHITE_LIGHT_DATA_REG = 0x05
    VEML_INTERRUPT_REG = 0x06

    # 16-bit register masks
    VEML_THRESH_MASK = 0x0
    VEML_GAIN_MASK = 0xE7FF
    VEML_INTEG_MASK = 0xFC3F
    VEML_PERS_PROT_MASK = 0xFFCF
    VEML_INT_EN_MASK = 0xFFFD
    VEML_SD_MASK = 0xFFFE
    VEML_POW_SAVE_EN_MASK = 0x06  # Most of this register is reserved
    VEML_POW_SAVE_MASK = 0x01  # Most of this register is reserved
    VEML_INT_MASK = 0xC000    

    # Register bit positions
    VEML_NO_SHIFT = 0x00
    VEML_INT_EN_POS = 0x01
    VEML_PSM_POS = 0x01
    VEML_PERS_PROT_POS = 0x04
    VEML_INTEG_POS = 0x06
    VEML_GAIN_POS = 0xB
    VEML_INT_POS = 0xE

    # Table of lux conversion values depending on the integration time and gain. 
    # The arrays represent the all possible integration times and the index of the
    # arrays represent the register's gain settings, which is directly analogous to
    # their bit representations.
    VEML_EIGHT_HIT = [0.0036, 0.0072, 0.0288, 0.0576]
    VEML_FOUR_HIT = [0.0072, 0.0144, 0.0576, 0.1152]
    VEML_TWO_HIT = [0.0144, 0.0288, 0.1152, 0.2304]
    VEML_ONE_HIT = [0.0288, 0.0576, 0.2304, 0.4608]
    VEML_FIFTY_IT = [0.0576, 0.1152, 0.4608, 0.9216]
    VEML_TWENTY_FIVE_IT = [0.1152, 0.2304, 0.9216, 1.8432]

    # Gain settings
    VEML_GAIN_1_8 = 0.125
    VEML_GAIN_1_4 = 0.25
    VEML_GAIN_1 = 1.0
    VEML_GAIN_2 = 2.0

    # Integration times
    VEML_INTEG_TIME_800 = 800
    VEML_INTEG_TIME_400 = 400
    VEML_INTEG_TIME_200 = 200
    VEML_INTEG_TIME_100 = 100
    VEML_INTEG_TIME_50 = 50
    VEML_INTEG_TIME_25 = 25

    def __init__(self, sda: int, scl: int, address=None):
        """!
        Constructor

        @param int, optional address: The I2C address to use for the device
            If not provided, the default address is used
        @param I2CDriver, optional i2c_driver: An existing i2c driver object
            If not provided, a driver object is created
        """

        # Load the I2C driver if one isn't provided
        self._i2c = MicroPythonI2C(sda, scl)

        # Use address if provided, otherwise pick the default
        if address in self.available_addresses:
            self.address = address
        else:
            # Default to first available address if it is not provided
            self.address = self.available_addresses[0]

            # Since the VEML6030 and the VEML7700 have different default addresses but both 
            # use the same overall driver, we should check all available addresses so that users don't
            # have to specify the address manually, but CAN if they are using this device concurrently with
            # other devices that have addresses within the available_addresses list.
            # TODO: alternative is to make subclasses for each device, but that would 
            # be more for users to have to keep track of.

            # Try to dynamically check if any of our available addresses are connected:
            for addr in self.available_addresses:
                if self._i2c.isDeviceConnected(addr):
                    self.address = addr
                    break

    def is_connected(self):
        """!
        Determines if this device is connected

        @return **bool** `True` if connected, otherwise `False`
        """
        # Check if connected by seeing if an ACK is received
        return self._i2c.isDeviceConnected(self.address)

    connected = property(is_connected)

    def begin(self):
        """!
        Initializes this device with default parameters

        @return **bool** Returns `True` if successful, otherwise `False`
        """
        # Confirm device is connected before doing anything
        if not self.is_connected():
            return False
        
        # VEML6030/7700 is powered down by default, so power it on!
        self.power_on()
        
        # Done!
        return True

    def set_gain(self, gain_val):
        """!
        Sets the gain

        @param gain_val: Gain, possible values:
            1/8, 1/4, 1, and 2
        :type: float
        """
        # Determine gain bits
        if gain_val == self.VEML_GAIN_1:
            gain_bits = 0x00
        elif gain_val == self.VEML_GAIN_2:
            gain_bits = 0x01
        elif gain_val == self.VEML_GAIN_1_8:
            gain_bits = 0x02
        elif gain_val == self.VEML_GAIN_1_4:
            gain_bits = 0x03
        else:
            return
        
        # Write these bits
        self._write_register(self.VEML_SETTING_REG, self.VEML_GAIN_MASK, gain_bits, self.VEML_GAIN_POS)

    def read_gain(self):
        """!
        Gets the gain

        @return **float** Gain, possible values:
            1/8, 1/4, 1, and 2
        """
        # Read the gain bits
        gain_bits = self._read_register(self.VEML_SETTING_REG)
        gain_bits &= ~self.VEML_GAIN_MASK
        gain_bits = (gain_bits >> self.VEML_GAIN_POS)

        # Determine the true gain
        if gain_bits == 0x00:
            return self.VEML_GAIN_1
        elif gain_bits == 0x01:
            return self.VEML_GAIN_2
        elif gain_bits == 0x02:
            return self.VEML_GAIN_1_8
        elif gain_bits == 0x03:
            return self.VEML_GAIN_1_4
        else:
            return self.VEML_UNKNOWN_ERROR

    def set_integ_time(self, time):
        """!
        Sets the integration time

        @param int time: Integration time in ms, possible values:
            25, 50, 100, 200, 400, and 800
        """
        # Determine integration time bits
        if time == self.VEML_INTEG_TIME_100:
            time_bits = 0x00
        elif time == self.VEML_INTEG_TIME_200:
            time_bits = 0x01
        elif time == self.VEML_INTEG_TIME_400:
            time_bits = 0x02
        elif time == self.VEML_INTEG_TIME_800:
            time_bits = 0x03
        elif time == self.VEML_INTEG_TIME_50:
            time_bits = 0x08
        elif time == self.VEML_INTEG_TIME_25:
            time_bits = 0x0C
        else:
            return
        
        # Write these bits
        self._write_register(self.VEML_SETTING_REG, self.VEML_INTEG_MASK, time_bits, self.VEML_INTEG_POS)

    def read_integ_time(self):
        """!
        Gets the integration time

        @return **int** Integration time, ms
        """
        # Read the integration time bits
        time_bits = self._read_register(self.VEML_SETTING_REG)
        time_bits &= ~self.VEML_INTEG_MASK
        time_bits = time_bits >> self.VEML_INTEG_POS

        # Determine the true integration time
        if time_bits == 0x00:
            return self.VEML_INTEG_TIME_100
        elif time_bits == 0x01:
            return self.VEML_INTEG_TIME_200
        elif time_bits == 0x02:
            return self.VEML_INTEG_TIME_400
        elif time_bits == 0x03:
            return self.VEML_INTEG_TIME_800
        elif time_bits == 0x08:
            return self.VEML_INTEG_TIME_50
        elif time_bits == 0x0C:
            return self.VEML_INTEG_TIME_25
        else:
            return self.VEML_UNKNOWN_ERROR

    def set_protect(self, prot_val):
        """!
        Sets the persistence protect number

        @param int prot_val: Protect number
        """
        # Determine protect number bits
        if prot_val == 1:
            prot_bits = 0x00
        elif prot_val == 2:
            prot_bits = 0x01
        elif prot_val == 4:
            prot_bits = 0x02
        elif prot_val == 8:
            prot_bits = 0x03
        else:
            return
        
        # Write these bits
        self._write_register(self.VEML_SETTING_REG, self.VEML_PERS_PROT_MASK, prot_bits, self.VEML_PERS_PROT_POS)

    def read_protect(self):
        """!
        Gets the persistence protect number

        @return **int** Protect number (or VEML_UNKOWN_ERROR on error)
        """
        # Read the protect number bits
        prot_bits = self._read_register(self.VEML_SETTING_REG)
        prot_bits &= ~self.VEML_PERS_PROT_MASK
        prot_bits = prot_bits >> self.VEML_PERS_PROT_POS

        # Determine the true protect number
        if prot_bits == 0x00:
            return 1
        elif prot_bits == 0x01:
            return 2
        elif prot_bits == 0x02:
            return 4
        elif prot_bits == 0x03:
            return 8
        else:
            return self.VEML_UNKNOWN_ERROR

    def enable_int(self):
        """!
        Enables interrupts
        """
        self._write_register(self.VEML_SETTING_REG, self.VEML_INT_EN_MASK, self.VEML_ENABLE, self.VEML_INT_EN_POS)

    def disable_int(self):
        """!
        Disables interrupts
        """
        self._write_register(self.VEML_SETTING_REG, self.VEML_INT_EN_MASK, self.VEML_DISABLE, self.VEML_INT_EN_POS)

    def read_int_setting(self):
        """!
        Gets whether interrupts are enabled

        @return **bool** `True` if interrupts are enabled, otherwise `False`
        """
        # Get interrupt bits
        int_setting = self._read_register(self.VEML_SETTING_REG)
        int_setting &= ~self.VEML_INT_EN_MASK
        int_setting = int_setting >> self.VEML_INT_EN_POS
        return bool(int_setting)

    def shut_down(self):
        """!
        Shuts down the device
        """
        self._write_register(self.VEML_SETTING_REG, self.VEML_SD_MASK, self.VEML_SHUTDOWN, self.VEML_NO_SHIFT)

    def power_on(self):
        """!
        Powers on the device
        """
        self._write_register(self.VEML_SETTING_REG, self.VEML_SD_MASK, self.VEML_POWER, self.VEML_NO_SHIFT)
        # Wait 4ms for power on to complete
        time.sleep(0.004)

    def enable_pow_save(self):
        """!
        Enables power saving mode
        """
        self._write_register(self.VEML_POWER_SAVE_REG, self.VEML_POW_SAVE_EN_MASK, self.VEML_ENABLE, self.VEML_NO_SHIFT)

    def disable_pow_save(self):
        """!
        Disables power saving mode
        """
        self._write_register(self.VEML_POWER_SAVE_REG, self.VEML_POW_SAVE_EN_MASK, self.VEML_DISABLE, self.VEML_NO_SHIFT)

    def read_pow_sav_enabled(self):
        """!
        Gets whether power saving is enabled

        @return **bool** `True` if power saving is enabled, otherwise `False`
        """
        pow_sav_enabled = self._read_register(self.VEML_POWER_SAVE_REG)
        pow_sav_enabled &= ~self.VEML_POW_SAVE_EN_MASK
        return bool(pow_sav_enabled)

    def set_pow_sav_mode(self, mode_val):
        """!
        Sets the power saving mode. See datasheet for the effects of each value

        @param int mode_val: Power saving mode number, can be 1-4
        """
        # Determine power saving mode bits
        if mode_val == 1:
            mode_bits = 0x00
        elif mode_val == 2:
            mode_bits = 0x01
        elif mode_val == 3:
            mode_bits = 0x02
        elif mode_val == 4:
            mode_bits = 0x03
        else:
            return
        
        # Write these bits
        self._write_register(self.VEML_POWER_SAVE_REG, self.VEML_POW_SAVE_MASK, mode_bits, self.VEML_PSM_POS)

    def read_pow_sav_mode(self):
        """!
        Gets the power saving mode. See datasheet for the effects of each value

        @return **int** Power saving mode number, can be 1-4 (or VEML_UNKOWN_ERROR on error)
        """
        # Read the power saving mode bits
        mode_bits = self._read_register(self.VEML_POWER_SAVE_REG)
        mode_bits &= ~self.VEML_POW_SAVE_MASK
        mode_bits = mode_bits >> self.VEML_PSM_POS

        # Determine the true power saving mode
        if mode_bits == 0:
            return 1
        elif mode_bits == 1:
            return 2
        elif mode_bits == 2:
            return 3
        elif mode_bits == 3:
            return 4
        else:
            return self.VEML_UNKNOWN_ERROR

    def read_interrupt(self):
        """!
        Gets whether an interrupt has triggered

        @return **int** Interrupt, can be the following:
            VEML_NO_INT, VEML_INT_HIGH, or VEML_INT_LOW (or VEML_UNKOWN_ERROR on error)
        """
        # Read the interrupt bits
        interrupt = self._read_register(self.VEML_INTERRUPT_REG)
        interrupt &= self.VEML_INT_MASK
        interrupt = interrupt >> self.VEML_INT_POS

        # Determine whether an interrupt has occurred
        if interrupt == 0:
            return self.VEML_NO_INT
        elif interrupt == 1:
            return self.VEML_INT_HIGH
        elif interrupt == 2:
            return self.VEML_INT_LOW
        else:
            return self.VEML_UNKNOWN_ERROR

    def set_int_low_thresh(self, lux_val):
        """!
        Sets the low threshold for interrupts

        @param float lux_val: Low threshold in lux
        """
        # Threshold cannot exceed 120k lux
        if lux_val < 0 or lux_val > 120000:
            return
        
        # Calculate bits and write them
        bits = self._calculate_bits(lux_val)
        self._write_register(self.VEML_L_THRESH_REG, self.VEML_THRESH_MASK, bits, self.VEML_NO_SHIFT)

    def read_low_thresh(self):
        """!
        Gets the low threshold for interrupts

        @return **float** Low threshold in lux
        """
        # Read bits and convert to lux
        bits = self._read_register(self.VEML_L_THRESH_REG)
        lux_val = self._calculate_lux(bits)
        return lux_val

    def set_int_high_thresh(self, lux_val):
        """!
        Sets the high threshold for interrupts

        @param float lux_val: High threshold in lux
        """
        # Threshold cannot exceed 120k lux
        if lux_val < 0 or lux_val > 120000:
            return
        
        # Calculate bits and write them
        bits = self._calculate_bits(lux_val)
        self._write_register(self.VEML_H_THRESH_REG, self.VEML_THRESH_MASK, bits, self.VEML_NO_SHIFT)

    def read_high_thresh(self):
        """!
        Gets the high threshold for interrupts

        @return **float** High threshold in lux
        """
        # Read bits and convert to lux
        bits = self._read_register(self.VEML_H_THRESH_REG)
        lux_val = self._calculate_lux(bits)
        return lux_val

    def read_light(self):
        """!
        Gets the measured ambient light in lux

        @return **float** Measure ambient light in lux
        """
        # Read bits and convert to lux
        light_bits = self._read_register(self.VEML_AMBIENT_LIGHT_DATA_REG)
        lux_val = self._calculate_lux(light_bits)

        # If > 1k lux, run compensation algorithm
        if lux_val > 1000:
            comp_lux = self._lux_compensation(lux_val)
            return comp_lux
        else:
            return lux_val

    def read_white_light(self):
        """!
        Gets the measured white light in lux

        @return **float** Measure white light in lux
        """
        # Read bits and convert to lux
        light_bits = self._read_register(self.VEML_WHITE_LIGHT_DATA_REG)
        lux_val = self._calculate_lux(light_bits)

        # If > 1k lux, run compensation algorithm
        if lux_val > 1000:
            comp_lux = self._lux_compensation(lux_val)
            return comp_lux
        else:
            return lux_val

    def _lux_compensation(self, lux_val):
        """!
        Compensates lux values over 1000

        @param float lux_val: Lux value

        @return **float** Compensated lux value
        """
        # Found in page 10 of datasheet
        comp_lux = (
            0.00000000000060135 * (lux_val ** 4)
            - 0.0000000093924 * (lux_val ** 3)
            + 0.000081488 * (lux_val ** 2)
            + 1.0023 * lux_val
        )
        return comp_lux

    def _calculate_lux(self, light_bits):
        """!
        Calculates lux value from raw bits

        @param int light_bits: Raw bits

        @return **float** Lux value (or VEML_UNKOWN_ERROR on error)
        """
        # Need to know the gain and integration time so we can adjust for them
        gain = self.read_gain()
        integ_time = self.read_integ_time()

        # Determine the lookup table index
        if gain == self.VEML_GAIN_2:
            conv_pos = 0
        elif gain == self.VEML_GAIN_1:
            conv_pos = 1
        elif gain == self.VEML_GAIN_1_4:
            conv_pos = 2
        elif gain == self.VEML_GAIN_1_8:
            conv_pos = 3
        else:
            return self.VEML_UNKNOWN_ERROR

        # Determine the lux conversion from the lookup table
        if integ_time == self.VEML_INTEG_TIME_800:
            lux_conv = self.VEML_EIGHT_HIT[conv_pos]
        elif integ_time == self.VEML_INTEG_TIME_400:
            lux_conv = self.VEML_FOUR_HIT[conv_pos]
        elif integ_time == self.VEML_INTEG_TIME_200:
            lux_conv = self.VEML_TWO_HIT[conv_pos]
        elif integ_time == self.VEML_INTEG_TIME_100:
            lux_conv = self.VEML_ONE_HIT[conv_pos]
        elif integ_time == self.VEML_INTEG_TIME_50:
            lux_conv = self.VEML_FIFTY_IT[conv_pos]
        elif integ_time == self.VEML_INTEG_TIME_25:
            lux_conv = self.VEML_TWENTY_FIVE_IT[conv_pos]
        else:
            return self.VEML_UNKNOWN_ERROR

        # Compute lux
        calculated_lux = lux_conv * light_bits
        return calculated_lux

    def _calculate_bits(self, lux_val):
        """!
        Calculates raw bits from lux value

        @param float lux_val: Lux value

        @return **int** Raw bits (or VEML_UNKOWN_ERROR on error)
        """
        # Need to know the gain and integration time so we can adjust for them
        gain = self.read_gain()
        integ_time = self.read_integ_time()

        # Determine the lookup table index
        if gain == self.VEML_GAIN_2:
            conv_pos = 0
        elif gain == self.VEML_GAIN_1:
            conv_pos = 1
        elif gain == self.VEML_GAIN_1_4:
            conv_pos = 2
        elif gain == self.VEML_GAIN_1_8:
            conv_pos = 3
        else:
            return self.VEML_UNKNOWN_ERROR

        # Determine the lux conversion from the lookup table
        if integ_time == self.VEML_INTEG_TIME_800:
            lux_conv = self.VEML_EIGHT_HIT[conv_pos]
        elif integ_time == self.VEML_INTEG_TIME_400:
            lux_conv = self.VEML_FOUR_HIT[conv_pos]
        elif integ_time == self.VEML_INTEG_TIME_200:
            lux_conv = self.VEML_TWO_HIT[conv_pos]
        elif integ_time == self.VEML_INTEG_TIME_100:
            lux_conv = self.VEML_ONE_HIT[conv_pos]
        elif integ_time == self.VEML_INTEG_TIME_50:
            lux_conv = self.VEML_FIFTY_IT[conv_pos]
        elif integ_time == self.VEML_INTEG_TIME_25:
            lux_conv = self.VEML_TWENTY_FIVE_IT[conv_pos]
        else:
            return self.VEML_UNKNOWN_ERROR

        # Compute raw bits
        calculated_bits = int(lux_val / lux_conv)
        return calculated_bits

    def _write_register(self, w_reg, mask, bits, start_position):
        """!
        Writes specific bits to a register

        @param int w_reg: Register address
        @param int mask: Bit mask
        @param int bits: Bits to write
        @param int start_position: Offset position
        """
        # Read current register value
        i2c_write = self._read_register(w_reg)

        # Clear bits in mask position, then write provided bits
        i2c_write &= mask
        i2c_write |= bits << start_position

        # Write new value back to register
        self._i2c.writeWord(self.address, w_reg, i2c_write)

    def _read_register(self, reg):
        """!
        Reads a register

        @param int reg: Register address

        @return **int** Register value
        """
        return self._i2c.readWord(self.address, reg)