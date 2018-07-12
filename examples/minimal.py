#
# Original work Copyright (c) 2014 Danny Zhu
# Modified work Copyright (c) 2018 Matthias Gazzari
#
# Licensed under the MIT license. See the LICENSE file for details.
#

import argparse
from myo_raw import MyoRaw, DataCategory, EMGMode


def emg_handler(emg, moving, characteristic_num):
    print('emg:', emg, moving, characteristic_num)

def imu_handler(quat, acc, gyro,):
    print('imu:', quat, acc, gyro)

def battery_handler(battery_level):
    print('battery level:', battery_level)


parser = argparse.ArgumentParser()
group = parser.add_mutually_exclusive_group()
group.add_argument('--tty', default=None, help='The Myo dongle device (autodetected if omitted)')
group.add_argument('--native', default=False, action='store_true', help='Use a native Bluetooth stack')
parser.add_argument('--mac', default=None, help='The Myo MAC address (arbitrarily detected if omitted)')
modes = ', '.join([str(item.value) + ': ' + item.name for item in EMGMode])
parser.add_argument('--emg_mode', type=int, default=EMGMode.RAW, choices=[m.value for m in EMGMode],
        help='Choose the EMG receiving mode ({0} - default: %(default)s)'.format(modes))
args = parser.parse_args()

# setup the BLED112 dongle or a native Bluetooth stack with bluepy and connect to a Myo armband
myo = MyoRaw(args.tty, args.native, args.mac)
# add handlers to process EMG, IMU and battery level data
myo.add_handler(DataCategory.EMG, emg_handler)
myo.add_handler(DataCategory.IMU, imu_handler)
myo.add_handler(DataCategory.BATTERY, battery_handler)
# subscribe to all data services
myo.subscribe(args.emg_mode)
# disable sleep to avoid disconnects while retrieving data
myo.set_sleep_mode(1)
# vibrate and change colors (green logo, blue bar) to signalise a successfull setup
myo.vibrate(1)
myo.set_leds([0, 255, 0], [0, 0, 255])

# run until terminated by the user
try:
    while True:
        myo.run(1)
except KeyboardInterrupt:
    pass
finally:
    myo.disconnect()
    print('Disconnected')
