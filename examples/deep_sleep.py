#
# Copyright (c) 2018 Matthias Gazzari
#
# Licensed under the MIT license. See the LICENSE file for details.
#

import argparse
from myo_raw import MyoRaw

parser = argparse.ArgumentParser()
group = parser.add_mutually_exclusive_group()
group.add_argument('--tty', default=None, help='The Myo dongle device (autodetected if omitted)')
group.add_argument('--native', default=False, action='store_true', help='Use a native Bluetooth stack')
parser.add_argument('--mac', default=None, help='The Myo MAC address (arbitrarily detected if omitted)')
args = parser.parse_args()

myo = MyoRaw(args.tty, args.native)
myo.connect(args.mac)
myo.deep_sleep()
