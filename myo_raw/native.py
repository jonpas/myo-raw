#
# Original work Copyright (c) 2014 Danny Zhu
# Modified work Copyright (c) 2018 Matthias Gazzari
#
# Licensed under the MIT license. See the LICENSE file for details.
#

from bluepy import btle

class Delegate(btle.DefaultDelegate):
    '''Store handlers to be called from a bluepy Peripheral on receiving notifications'''

    def __init__(self):
        super().__init__()
        self.handler = None

    def handleNotification(self, cHandle, data):
        if self.handler:
            self.handler(cHandle, data)

class Native(btle.Peripheral):
    '''Non-Myo-specific Bluetooth backend based on a bluepy to use standard Bluetooth adapters.'''

    def __init__(self):
        super().__init__()
        self.withDelegate(Delegate())
        print('using bluepy backend')

    @staticmethod
    def scan(target_uuid, target_address=None):
        print('scanning...')
        scanner = btle.Scanner()
        while True:
            devices = scanner.scan(timeout=1)
            for dev in devices:
                uuid = next(item[2] for item in dev.getScanData() if item[0] == 6)
                if target_uuid == uuid:
                    print('found a Bluetooth device (MAC address: {0})'.format(dev.addr))
                    if target_address is None or target_address.lower() == dev.addr:
                        return dev.addr

    @property
    def handler(self):
        return self.delegate.handler

    @handler.setter
    def handler(self, handler):
        self.delegate.handler = handler

    def recv_packet(self, timeout=None):
        self.waitForNotifications(timeout)

    def read_attr(self, attr):
        return self.readCharacteristic(attr)

    def write_attr(self, attr, val, wait_response=True):
        return self.writeCharacteristic(attr, val, withResponse=wait_response)
