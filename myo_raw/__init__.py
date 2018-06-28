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
from .bluetooth import BT

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


class MyoRaw(object):
    '''Implements the Myo-specific communication protocol.'''

    def __init__(self, tty=None):
        self.bt = BT(tty)
        self.emg_handlers = []
        self.imu_handlers = []
        self.arm_handlers = []
        self.pose_handlers = []
        self.battery_handlers = []

    def run(self, timeout=None):
        self.bt.recv_packet(timeout)

    def connect(self, mac=None, filtered=False):
        # stop everything from before
        self.bt.end_scan()
        self.bt.disconnect(0)
        self.bt.disconnect(1)
        self.bt.disconnect(2)

        # start scanning
        print('scanning...')
        self.bt.discover()
        while True:
            p = self.bt.recv_packet()
            print('scan response:', p)

            if p.payload.endswith(b'\x06\x42\x48\x12\x4A\x7F\x2C\x48\x47\xB9\xDE\x04\xA9\x01\x00\x06\xD5'):
                addr = list(list(p.payload[2:8]))
                addr_str = ':'.join(format(item, '02x') for item in reversed(addr))
                print('MAC address:', addr_str)
                if mac is None or mac.lower() == addr_str:
                    break
        self.bt.end_scan()

        # connect and wait for status event
        self.bt.connect(addr)

        # get firmware version
        fw = self.read_attr(0x17)
        _, _, _, _, v0, v1, v2, v3 = struct.unpack('<BHBBHHHH', fw.payload)
        print('firmware version: %d.%d.%d.%d' % (v0, v1, v2, v3))

        self.old = (v0 == 0)

        if self.old:
            # don't know what these do; Myo Connect sends them, though we get data
            # fine without them
            self.write_attr(0x19, b'\x01\x02\x00\x00')
            # Subscribe for notifications from 4 EMG data channels
            self.write_attr(0x2f, b'\x01\x00')
            self.write_attr(0x2c, b'\x01\x00')
            self.write_attr(0x32, b'\x01\x00')
            self.write_attr(0x35, b'\x01\x00')

            # suscribe to EMG notifications to enable EMG data
            self.write_attr(0x28, b'\x01\x00')
            # suscribe to IMU notifications to enable IMU data
            self.write_attr(0x1d, b'\x01\x00')

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
            self.write_attr(0x19, struct.pack('<BBBBHBBBBB', 2, 9, 2, 1, C, emg_smooth, C // emg_hz, imu_hz, 0, 0))

        else:
            name = self.read_attr(0x03)
            print('device name: %s' % name.payload)

            # suscribe to IMU notifications to enable IMU data
            self.write_attr(0x1d, b'\x01\x00')
            # suscribe to classifier indications to enable on/off arm notifications
            self.write_attr(0x24, b'\x02\x00')
            # enable EMG notifications
            ''' To get raw EMG signals, we subscribe to the four EMG notification
            characteristics by writing a 0x0100 command to the corresponding handles.
            '''
            if not filtered:
                self.write_attr(0x2c, b'\x01\x00')  # Suscribe to EmgData0Characteristic
                self.write_attr(0x2f, b'\x01\x00')  # Suscribe to EmgData1Characteristic
                self.write_attr(0x32, b'\x01\x00')  # Suscribe to EmgData2Characteristic
                self.write_attr(0x35, b'\x01\x00')  # Suscribe to EmgData3Characteristic

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
                self.write_attr(0x19, b'\x01\x03\x02\x01\x01')

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
                self.write_attr(0x28, b'\x01\x00')
                # set EMG and IMU, payload size = 3, EMG on, IMU on, classifier on
                self.write_attr(0x19, b'\x01\x03\x01\x01\x01')
            # enable battery notifications
            self.write_attr(0x12, b'\x01\x10')

        # add data handlers
        def handle_data(p):
            if (p.cls, p.cmd) != (4, 5):
                return

            _, attr, typ = struct.unpack('<BHB', p.payload[:4])
            pay = p.payload[5:]

            if attr == 0x27:
                # Unpack a 17 byte array, first 16 are 8 unsigned shorts, last one an unsigned char
                vals = struct.unpack('<8HB', pay)
                # not entirely sure what the last byte is, but it's a bitmask that
                # seems to indicate which sensors think they're being moved around or
                # something
                emg = vals[:8]
                moving = vals[8]
                self.on_emg(emg, moving)
            # Read notification handles corresponding to the for EMG characteristics
            elif attr == 0x2b or attr == 0x2e or attr == 0x31 or attr == 0x34:
                '''According to http://developerblog.myo.com/myocraft-emg-in-the-bluetooth-protocol/
                each characteristic sends two secuential readings in each update,
                so the received payload is split in two samples. According to the
                Myo BLE specification, the data type of the EMG samples is int8_t.
                '''
                emg1 = struct.unpack('<8b', pay[:8])
                emg2 = struct.unpack('<8b', pay[8:])
                self.on_emg(emg1, 0)
                self.on_emg(emg2, 0)
            # Read IMU characteristic handle
            elif attr == 0x1c:
                vals = struct.unpack('<10h', pay)
                quat = vals[:4]
                acc = vals[4:7]
                gyro = vals[7:10]
                self.on_imu(quat, acc, gyro)
            # Read classifier characteristic handle
            elif attr == 0x23:
                # note that older versions of the Myo send three bytes
                # whereas newer ones send six bytes
                typ, val, xdir = struct.unpack('<3B', pay[:3])

                if typ == 1:  # on arm
                    self.on_arm(Arm(val), XDirection(xdir))
                elif typ == 2:  # removed from arm
                    self.on_arm(Arm.UNKNOWN, XDirection.UNKNOWN)
                elif typ == 3:  # pose
                    self.on_pose(Pose(val))
            # Read battery characteristic handle
            elif attr == 0x11:
                battery_level = ord(pay)
                self.on_battery(battery_level)
            else:
                print('data with unknown attr: %02X %s' % (attr, p))

        self.bt.add_handler(handle_data)

    def write_attr(self, attr, val):
        self.bt.write_attr(attr, val)

    def read_attr(self, attr):
        return self.bt.read_attr(attr)

    def disconnect(self):
        self.bt.disconnect(self.bt.conn)

    def sleep_mode(self, mode):
        self.write_attr(0x19, struct.pack('<3B', 9, 1, mode))

    def power_off(self):
        self.write_attr(0x19, b'\x04\x00')

    def vibrate(self, length):
        if length in range(1, 4):
            # first byte tells it to vibrate; purpose of second byte is unknown (payload size?)
            self.write_attr(0x19, struct.pack('<3B', 3, 1, length))

    def set_leds(self, logo, line):
        self.write_attr(0x19, struct.pack('<8B', 6, 6, *(logo + line)))

    # def get_battery_level(self):
    #     battery_level = self.read_attr(0x11)
    #     return ord(battery_level.payload[5])

    def add_emg_handler(self, h):
        self.emg_handlers.append(h)

    def pop_emg_handler(self, i=-1):
        return self.emg_handlers.pop(i)

    def clear_emg_handlers(self):
        self.emg_handlers.clear()

    def add_imu_handler(self, h):
        self.imu_handlers.append(h)

    def pop_imu_handler(self, i=-1):
        return self.imu_handlers.pop(i)

    def clear_imu_handlers(self):
        self.imu_handlers.clear()

    def add_pose_handler(self, h):
        self.pose_handlers.append(h)

    def pop_pose_handler(self, i=-1):
        return self.pose_handlers.pop(i)

    def clear_pose_handlers(self):
        self.pose_handlers.clear()

    def add_arm_handler(self, h):
        self.arm_handlers.append(h)

    def pop_arm_handler(self, i=-1):
        return self.arm_handlers.pop(i)

    def clear_arm_handlers(self):
        self.arm_handlers.clear()

    def add_battery_handler(self, h):
        self.battery_handlers.append(h)

    def pop_battery_handler(self, i=-1):
        return self.battery_handlers.pop(i)

    def clear_battery_handlers(self):
        self.battery_handlers.clear()

    def on_emg(self, emg, moving):
        for h in self.emg_handlers:
            h(emg, moving)

    def on_imu(self, quat, acc, gyro):
        for h in self.imu_handlers:
            h(quat, acc, gyro)

    def on_pose(self, p):
        for h in self.pose_handlers:
            h(p)

    def on_arm(self, arm, xdir):
        for h in self.arm_handlers:
            h(arm, xdir)

    def on_battery(self, battery_level):
        for h in self.battery_handlers:
            h(battery_level)
