#
# Original work Copyright (c) 2014 Danny Zhu
# Modified work Copyright (c) 2017 Alvaro Villoslada
# Modified work Copyright (c) 2017 Fernando Cosentino
# Modified work Copyright (c) 2018 Google LLC
# Modified work Copyright (c) 2018 Matthias Gazzari
#
# Licensed under the MIT license. See the LICENSE file for details.
#

import enum
import struct
import time
from .bled112 import BLED112
try:
    from .native import Native
except ImportError:
    NATIVE_SUPPORT = False
else:
    NATIVE_SUPPORT = True


class Arm(enum.Enum):
    UNKNOWN = 0
    RIGHT = 1
    LEFT = 2


class XDirection(enum.Enum):
    UNKNOWN = 0
    X_TOWARD_WRIST = 1
    X_TOWARD_ELBOW = 2


class Pose(enum.Enum):
    REST = 0
    FIST = 1
    WAVE_IN = 2
    WAVE_OUT = 3
    FINGERS_SPREAD = 4
    THUMB_TO_PINKY = 5
    UNKNOWN = 255


class DataCategory(enum.Enum):
    '''Categories of data available from the Myo armband'''
    ARM, BATTERY, EMG, IMU, POSE = range(5)


class EMGMode(enum.IntEnum):
    '''Modes of EMG data (sampling rate and applied filters)'''
    OFF = 0x00
    SMOOTHED = 0x01
    RAW_FILTERED = 0x02
    RAW = 0x03


class IMUMode(enum.IntEnum):
    '''Modes of IMU data'''
    OFF = 0x00
    ON = 0x01
    EVENTS = 0x02
    ALL = 0x03
    RAW = 0x04


class MyoRaw():
    '''Implements the Myo-specific communication protocol.'''

    def __init__(self, tty=None, native=False, mac=None):
        '''
        Scan and connect to a Myo armband using either the BLED112 or a native Bluetooth adapter

        :param tty: the device name of a Bluegiga BLED112 adapter
        :param native: if true try to use a native Bluetooth adapter (Linux only)
        :param mac: the MAC address of the Myo (randomly chosen if None)
        '''
        if native and not NATIVE_SUPPORT:
            raise ImportError('bluepy is required to use a native Bluetooth adapter')
        self.backend = Native() if native else BLED112(tty)
        self.native = native
        self.handlers = {data_category:[] for data_category in DataCategory}

        # scan and connect to a Myo armband and extract the firmware version
        mac = self.backend.scan('4248124a7f2c4847b9de04a9010006d5', mac)
        print('connecting to the Myo armband: {0}'.format(mac))
        self.backend.connect(mac)
        firmware = self.backend.read_attr(0x17)
        self.version = struct.unpack('<HHHH', firmware)

        # print device name, current battery level and firmware version
        print('device name: {}'.format(self.get_name()))
        print('battery level: {} %'.format(self.get_battery_level()))
        print('firmware version: %d.%d.%d.%d' % self.version)

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        self.disconnect()

    def run(self, timeout=None):
        '''
        Block until a packet is received or until the given timeout has elapsed

        :params timeout: the maximum amount of time to wait for a packet
        '''
        self.backend.recv_packet(timeout)

    def subscribe(self, emg_mode=EMGMode.RAW, imu_mode=IMUMode.ON, classifier=True, battery=True):
        '''
        Subscribe to chosen data channels. Note that the parameters have no influcence when using a
        Myo with version less than 1.0.0.0. In this case only EMG and IMU data are enabled.

        :param emg_mode: the mode of the EMG data stream (sampling rate and filters)

          :0: deactivate EMG data
          :1: 50 Hz sampling rate, smoothed and rectified signals ("hidden" EMG mode)
          :2: 200 Hz sampling rate, power line noise filters (50 and 60 Hz notch filters)
          :3: 200 Hz sampling rate, raw data
        :param imu_mode: the mode of the IMU data stream
        :param classifier: whether to enable the on-board classifier indications or not
        :param battery: whether to enable battery notifications or not
        '''

        if self.version < (1, 0, 0, 0):
            # don't know what these do; Myo Connect sends them, though we get data fine without them
            self.backend.write_attr(0x19, b'\x01\x02\x00\x00')
            # subscribe to notifications of the four official EMG characteristics
            self.backend.write_attr(0x2f, b'\x01\x00')
            self.backend.write_attr(0x2c, b'\x01\x00')
            self.backend.write_attr(0x32, b'\x01\x00')
            self.backend.write_attr(0x35, b'\x01\x00')
            # subscribe to notifications of the "hidden" EMG characteristics
            self.backend.write_attr(0x28, b'\x01\x00')
            # subscribe to notifications of the IMU characteristic
            self.backend.write_attr(0x1d, b'\x01\x00')

            # Sampling rate of the underlying EMG sensor, capped to 1000. If it's less than 1000,
            # emg_hz is correct. If it is greater, the actual framerate starts dropping inversely.
            # Also, if this is much less than 1000, EMG data becomes slower to respond to changes.
            # In conclusion, 1000 is probably a good value.
            f_s = 1000
            emg_hz = 50
            # strength of low-pass filtering of EMG data
            emg_smooth = 100
            imu_hz = 50
            # send sensor parameters, or we don't get any data
            data = struct.pack('<4BH5B', 2, 9, 2, 1, f_s, emg_smooth, f_s // emg_hz, imu_hz, 0, 0)
            self.backend.write_attr(0x19, data)
        else:
            # subscribe to notifications of the IMU characteristic
            if imu_mode:
                self.backend.write_attr(0x1d, b'\x01\x00')
            # subscribe to indications of the classifier (arm on/off, pose, etc.) characteristic
            if classifier:
                self.backend.write_attr(0x24, b'\x02\x00')
            # subscribe to notifications of the battery characteristic
            if battery:
                self.backend.write_attr(0x12, b'\x01\x10')
            # subscribe to notifications of the EMG characteristic(s)
            if emg_mode in [EMGMode.RAW, EMGMode.RAW_FILTERED]:
                # subscribe to notifications of the four official EMG characteristics
                self.backend.write_attr(0x2c, b'\x01\x00')  # Suscribe to EmgData0Characteristic
                self.backend.write_attr(0x2f, b'\x01\x00')  # Suscribe to EmgData1Characteristic
                self.backend.write_attr(0x32, b'\x01\x00')  # Suscribe to EmgData2Characteristic
                self.backend.write_attr(0x35, b'\x01\x00')  # Suscribe to EmgData3Characteristic
            elif emg_mode == EMGMode.SMOOTHED:
                # subscribe to notifications of the "hidden" (not listed in the myohw_services enum
                # of the official BLE specification from Thalmic Labs) EMG characteristic
                self.backend.write_attr(0x28, b'\x01\x00')

            # Activate EMG, IMU and classifier notifications. Note that sending a 0x01 for the EMG
            # mode (not listed on the myohw_emg_mode_t struct of the Myo BLE specification) will
            # enable the transmission of a stream of low-pass filtered EMG signals from the eight
            # sensor pods of the Myo armband (the "hidden" mode mentioned above).
            # Instead of getting raw EMG signals, we get rectified and smoothed signals, a measure
            # of the amplitude of the EMG (which is useful as a measure of muscle strength, but is
            # not as useful as a truly raw signal).
            # command breakdown: set EMG and IMU, payload size = 3, EMG, IMU and classifier modes
            self.backend.write_attr(0x19, b'\x01\x03' + bytes([emg_mode, imu_mode, classifier]))

        # add data handlers
        def handle_data(attr, pay):
            cur_time = time.time()
            if attr == 0x27:
                # Unpack a 17 byte array, first 16 are 8 unsigned shorts, last one an unsigned char
                # not entirely sure what the last byte is, but it's a bitmask that seems to indicate
                # which sensors think they're being moved around or something
                emg = struct.unpack('<8H', pay[:16])
                moving = pay[16]
                self._call_handlers(DataCategory.EMG, cur_time, emg, moving, None)
            # Read notification handles corresponding to the for EMG characteristics
            elif attr in (0x2b, 0x2e, 0x31, 0x34):
                # According to http://developerblog.myo.com/myocraft-emg-in-the-bluetooth-protocol/
                # each characteristic sends two sequential readings in each update, so the received
                # payload is split in two samples. According to the Myo BLE specification, the data
                # type of the EMG samples is int8_t.
                emg1 = struct.unpack('<8b', pay[:8])
                emg2 = struct.unpack('<8b', pay[8:])
                characteristic_num = int((attr - 1) / 3 - 14)
                self._call_handlers(DataCategory.EMG, cur_time, emg1, None, characteristic_num)
                self._call_handlers(DataCategory.EMG, cur_time, emg2, None, characteristic_num)
            # Read IMU characteristic handle
            elif attr == 0x1c:
                quat = struct.unpack('<4h', pay[:8])
                acc = struct.unpack('<3h', pay[8:14])
                gyro = struct.unpack('<3h', pay[14:20])
                self._call_handlers(DataCategory.IMU, cur_time, quat, acc, gyro)
            # Read classifier characteristic handle
            elif attr == 0x23:
                # note that older Myo versions send three bytes whereas newer ones send six bytes
                typ, val, xdir = struct.unpack('<3B', pay[:3])
                if typ == 1:  # on arm
                    self._call_handlers(DataCategory.ARM, cur_time, Arm(val), XDirection(xdir))
                elif typ == 2:  # removed from arm
                    self._call_handlers(DataCategory.ARM, cur_time, Arm.UNKNOWN, XDirection.UNKNOWN)
                elif typ == 3:  # pose
                    self._call_handlers(DataCategory.POSE, cur_time, Pose(val))
            # Read battery characteristic handle
            elif attr == 0x11:
                battery_level = ord(pay)
                self._call_handlers(DataCategory.BATTERY, cur_time, battery_level)
            else:
                print('data with unknown attr: %02X %s' % (attr, pay))

        # wrap the handle_data function to be able to process BLED112 packets
        def wrapped_handle_data(packet):
            if (packet.cls, packet.cmd) != (4, 5):
                return
            _, attr, _ = struct.unpack('<BHB', packet.payload[:4])
            pay = packet.payload[5:]
            handle_data(attr, pay)

        # add the right data handling function for the chosen backend
        self.backend.add_handler(handle_data if self.native else wrapped_handle_data)

    def disconnect(self):
        '''
        Disconnect from the Myo armband
        '''
        self.backend.clear_handler()
        self.backend.disconnect()

    def set_sleep_mode(self, mode):
        '''
        Set the sleep mode of the Myo armband

        :params mode: the sleep mode - 0: sleep after a period of inactiviy, 1: disable sleep
        '''
        assert mode in [0, 1], 'mode must be 0 or 1'
        self.backend.write_attr(0x19, struct.pack('<3B', 0x09, 1, mode))

    def deep_sleep(self):
        '''
        Put the Myo armband into a deep sleep state (reactivate by charging it over USB)

        '''
        self.backend.write_attr(0x19, struct.pack('<2B', 0x04, 0), wait_response=False)

    def vibrate(self, length):
        '''
        Vibrate the Myo armband

        :params length: the vibration duration - 1: short, 2: medium, 3: long
        '''
        assert length in [1, 2, 3], 'length must be 1, 2, or 3'
        self.backend.write_attr(0x19, struct.pack('<3B', 0x03, 1, length))

    def set_leds(self, logo, line):
        '''
        Set the colors of the logo LED and the line LED

        :params logo: the RGB (iterable of integers from 0 to 255) logo color value
        :params line: the RGB (iterable of integers from 0 to 255) line color value
        '''
        self.backend.write_attr(0x19, struct.pack('<8B', 0x06, 6, *(logo + line)))

    def get_battery_level(self):
        '''
        Retrieve the current battery level percentage

        :returns: the current battery level
        '''
        return struct.unpack('<B', self.backend.read_attr(0x11))[0]

    def set_name(self, name):
        '''
        Set the name of the Myo armband

        :params name: the name to be set
        '''
        self.backend.write_attr(0x03, name.encode('utf-8'))

    def get_name(self):
        '''
        Get the name of the Myo armband

        :returns: the name
        '''
        return self.backend.read_attr(0x03).decode('utf-8')

    def add_handler(self, data_category, handler):
        '''
        Add a handler to process data of a specific category

        :param data_category: data category of the handler function
        :param handler: function to be called
        '''
        self.handlers[data_category].append(handler)

    def pop_handler(self, data_category, index=-1):
        '''
        Remove and return the handler of a specific data category at index (default last)

        :param data_category: data category of the handler function
        :param index: index of the handler to be removed and returned
        :returns: the removed handler
        '''
        return self.handlers[data_category].pop(index)

    def clear_handler(self, data_category):
        '''
        Remove all handlers of a given data category

        :param data_category: data category of the handler function
        '''
        self.handlers[data_category].clear()

    def _call_handlers(self, data_category, *args):
        '''
        Call all handlers of a given data category

        :param data_category: data category of the handler function
        '''
        for handler in self.handlers[data_category]:
            handler(*args)
