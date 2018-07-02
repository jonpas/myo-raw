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
from .bled112 import BLED112
try:
    from .native import Native
except ImportError:
    native_support = False
else:
    native_support = True


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

class MyoRaw(object):
    '''Implements the Myo-specific communication protocol.'''

    def __init__(self, tty=None, native=False):
        if native and not native_support:
            raise ImportError('bluepy is required to use a native Bluetooth adapter')
        self.backend = Native() if native else BLED112(tty)
        self.native = native
        self.handlers = {data_category:[] for data_category in DataCategory}

    def run(self, timeout=None):
        self.backend.recv_packet(timeout)

    def connect(self, mac=None, filtered=False):
        # scan for a Myo armband
        mac = self.backend.scan('4248124a7f2c4847b9de04a9010006d5', mac)
        print('connecting to the Myo armband: {0}'.format(mac))
        # connect to a Myo armband
        self.backend.connect(mac)

        # get firmware version
        firmware = self.backend.read_attr(0x17)
        version = struct.unpack('<HHHH', firmware)
        print('firmware version: %d.%d.%d.%d' % version)

        if version < (1, 0, 0, 0):
            # don't know what these do; Myo Connect sends them, though we get data
            # fine without them
            self.backend.write_attr(0x19, b'\x01\x02\x00\x00')
            # Subscribe for notifications from 4 EMG data channels
            self.backend.write_attr(0x2f, b'\x01\x00')
            self.backend.write_attr(0x2c, b'\x01\x00')
            self.backend.write_attr(0x32, b'\x01\x00')
            self.backend.write_attr(0x35, b'\x01\x00')

            # suscribe to EMG notifications to enable EMG data
            self.backend.write_attr(0x28, b'\x01\x00')
            # suscribe to IMU notifications to enable IMU data
            self.backend.write_attr(0x1d, b'\x01\x00')

            # Sampling rate of the underlying EMG sensor, capped to 1000. If it's
            # less than 1000, emg_hz is correct. If it is greater, the actual
            # framerate starts dropping inversely. Also, if this is much less than
            # 1000, EMG data becomes slower to respond to changes. In conclusion,
            # 1000 is probably a good value.
            C = 1000
            emg_hz = 50
            # strength of low-pass filtering of EMG data
            emg_smooth = 100

            imu_hz = 50

            # send sensor parameters, or we don't get any data
            self.backend.write_attr(0x19, struct.pack('<BBBBHBBBBB', 2, 9, 2, 1, C, emg_smooth, C // emg_hz, imu_hz, 0, 0))

        else:
            name = self.backend.read_attr(0x03)
            print('device name: %s' % name.decode('utf-8'))

            # suscribe to IMU notifications to enable IMU data
            self.backend.write_attr(0x1d, b'\x01\x00')
            # suscribe to classifier indications to enable on/off arm notifications
            self.backend.write_attr(0x24, b'\x02\x00')
            # enable EMG notifications
            ''' To get raw EMG signals, we subscribe to the four EMG notification
            characteristics by writing a 0x0100 command to the corresponding handles.
            '''
            if not filtered:
                self.backend.write_attr(0x2c, b'\x01\x00')  # Suscribe to EmgData0Characteristic
                self.backend.write_attr(0x2f, b'\x01\x00')  # Suscribe to EmgData1Characteristic
                self.backend.write_attr(0x32, b'\x01\x00')  # Suscribe to EmgData2Characteristic
                self.backend.write_attr(0x35, b'\x01\x00')  # Suscribe to EmgData3Characteristic

            '''Bytes sent to handle 0x19 (command characteristic) have the following
            format: [command, payload_size, EMG mode, IMU mode, classifier mode]
            According to the Myo BLE specification, the commands are:
                0x01 -> set EMG and IMU
                0x03 -> 3 bytes of payload
                0x02 -> send 50Hz filtered signals
                0x01 -> send IMU data streams
                0x01 -> send classifier events
            '''
            if not filtered:
                self.backend.write_attr(0x19, b'\x01\x03\x02\x01\x01')

            '''Sending this sequence for v1.0 firmware seems to enable both raw data and
            pose notifications.
            '''

            '''By writting a 0x0100 command to handle 0x28, some kind of "hidden" EMG
            notification characteristic is activated. This characteristic is not
            listed on the Myo services of the offical BLE specification from Thalmic
            Labs. Also, in the second line where we tell the Myo to enable EMG and
            IMU data streams and classifier events, the 0x01 command wich corresponds
            to the EMG mode is not listed on the myohw_emg_mode_t struct of the Myo
            BLE specification.
            These two lines, besides enabling the IMU and the classifier, enable the
            transmission of a stream of low-pass filtered EMG signals from the eight
            sensor pods of the Myo armband (the "hidden" mode I mentioned above).
            Instead of getting the raw EMG signals, we get rectified and smoothed
            signals, a measure of the amplitude of the EMG (which is useful to have
            a measure of muscle strength, but are not as useful as a truly raw signal).
            '''
            if filtered:
                # suscribe to EMG notifications (not needed for raw signals)
                self.backend.write_attr(0x28, b'\x01\x00')
                # set EMG and IMU, payload size = 3, EMG on, IMU on, classifier on
                self.backend.write_attr(0x19, b'\x01\x03\x01\x01\x01')
            # enable battery notifications
            self.backend.write_attr(0x12, b'\x01\x10')

        # add data handlers
        def handle_data(attr, pay):
            if attr == 0x27:
                # Unpack a 17 byte array, first 16 are 8 unsigned shorts, last one an unsigned char
                vals = struct.unpack('<8HB', pay)
                # not entirely sure what the last byte is, but it's a bitmask that
                # seems to indicate which sensors think they're being moved around or
                # something
                emg = vals[:8]
                moving = vals[8]
                self._call_handlers(DataCategory.EMG, emg, moving)
            # Read notification handles corresponding to the for EMG characteristics
            elif attr == 0x2b or attr == 0x2e or attr == 0x31 or attr == 0x34:
                '''According to http://developerblog.myo.com/myocraft-emg-in-the-bluetooth-protocol/
                each characteristic sends two secuential readings in each update,
                so the received payload is split in two samples. According to the
                Myo BLE specification, the data type of the EMG samples is int8_t.
                '''
                emg1 = struct.unpack('<8b', pay[:8])
                emg2 = struct.unpack('<8b', pay[8:])
                self._call_handlers(DataCategory.EMG, emg1, 0)
                self._call_handlers(DataCategory.EMG, emg2, 0)
            # Read IMU characteristic handle
            elif attr == 0x1c:
                vals = struct.unpack('<10h', pay)
                quat = vals[:4]
                acc = vals[4:7]
                gyro = vals[7:10]
                self._call_handlers(DataCategory.IMU, quat, acc, gyro)
            # Read classifier characteristic handle
            elif attr == 0x23:
                # note that older versions of the Myo send three bytes
                # whereas newer ones send six bytes
                typ, val, xdir = struct.unpack('<3B', pay[:3])

                if typ == 1:  # on arm
                    self._call_handlers(DataCategory.ARM, Arm(val), XDirection(xdir))
                elif typ == 2:  # removed from arm
                    self._call_handlers(DataCategory.ARM, Arm.UNKNOWN, XDirection.UNKNOWN)
                elif typ == 3:  # pose
                    self._call_handlers(DataCategory.POSE, Pose(val))
            # Read battery characteristic handle
            elif attr == 0x11:
                battery_level = ord(pay)
                self._call_handlers(DataCategory.BATTERY, battery_level)
            else:
                print('data with unknown attr: %02X %s' % (attr, pay))

        def wrapped_handle_data(packet):
            if (packet.cls, packet.cmd) != (4, 5):
                return
            _, attr, _ = struct.unpack('<BHB', packet.payload[:4])
            pay = packet.payload[5:]
            handle_data(attr, pay)

        self.backend.add_handler(handle_data if self.native else wrapped_handle_data)

    def disconnect(self):
        self.backend.disconnect()

    def set_sleep_mode(self, mode):
        assert mode in [0, 1], 'mode must be 0 or 1'
        self.backend.write_attr(0x19, struct.pack('<3B', 0x09, 1, mode))

    def power_off(self):
        self.backend.write_attr(0x19, struct.pack('<2B', 0x04, 0))

    def vibrate(self, length):
        assert length in [1, 2, 3], 'length must be 1, 2, or 3'
        self.backend.write_attr(0x19, struct.pack('<3B', 0x03, 1, length))

    def set_leds(self, logo, line):
        self.backend.write_attr(0x19, struct.pack('<8B', 0x06, 6, *(logo + line)))

    # def get_battery_level(self):
    #     battery_level = self.backend.read_attr(0x11)
    #     return ord(battery_level[0])

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
