#
# Original work Copyright (c) 2014 Danny Zhu
# Modified work Copyright (c) 2017 Alvaro Villoslada
# Modified work Copyright (c) 2017 Fernando Cosentino
# Modified work Copyright (c) 2018 Matthias Gazzari
#
# Licensed under the MIT license. See the LICENSE file for details.
#

import struct
import threading
import time
import re
import serial
from serial.tools import list_ports

class Packet(object):
    def __init__(self, ords):
        self.typ = ords[0]
        self.cls = ords[2]
        self.cmd = ords[3]
        self.payload = bytes(ords[4:])

    def __repr__(self):
        return 'Packet(%02X, %02X, %02X, [%s])' % \
            (self.typ, self.cls, self.cmd,
             ' '.join('%02X' % b for b in list(self.payload)))


class BLED112(object):
    '''Implements the non-Myo-specific details of the Bluetooth protocol.'''
    def __init__(self, tty):
        if tty is None:
            tty = self.detect_tty()
        if tty is None:
            raise ValueError('Myo dongle not found!')
        self.conn = None
        self.ser = serial.Serial(port=tty, baudrate=9600, dsrdtr=1)
        self.buf = []
        self.lock = threading.Lock()
        self.handlers = []

    @staticmethod
    def detect_tty():
        '''Try to find a Bluegiga BLED112 dongle'''
        for port, desc, hwid in list_ports.comports():
            if re.search(r'PID=2458:0*1', hwid):
                print('using "{0}" at port {1}'.format(desc, port))
                return port
        return None

    # internal data-handling methods
    def recv_packet(self, timeout=None):
        t0 = time.time()
        self.ser.timeout = None
        while timeout is None or time.time() < t0 + timeout:
            if timeout is not None:
                self.ser.timeout = t0 + timeout - time.time()
            c = self.ser.read()
            if not c:
                return None

            ret = self.proc_byte(ord(c))
            if ret:
                if ret.typ == 0x80:
                    self.handle_event(ret)
                return ret

    def recv_packets(self, timeout=.5):
        res = []
        t0 = time.time()
        while time.time() < t0 + timeout:
            p = self.recv_packet(t0 + timeout - time.time())
            if not p:
                return res
            res.append(p)
        return res

    def proc_byte(self, c):
        if not self.buf:
            if c in [0x00, 0x80, 0x08, 0x88]:  # [BLE response pkt, BLE event pkt, wifi response pkt, wifi event pkt]
                self.buf.append(c)
            return None
        elif len(self.buf) == 1:
            self.buf.append(c)
            self.packet_len = 4 + (self.buf[0] & 0x07) + self.buf[1]
            return None
        else:
            self.buf.append(c)

        if self.packet_len and len(self.buf) == self.packet_len:
            p = Packet(self.buf)
            self.buf = []
            return p
        return None

    def handle_event(self, p):
        for h in self.handlers:
            h(p)

    def add_handler(self, h):
        self.handlers.append(h)

    def remove_handler(self, h):
        try:
            self.handlers.remove(h)
        except ValueError:
            pass

    def wait_event(self, cls, cmd):
        res = [None]

        def h(p):
            if p.cls == cls and p.cmd == cmd:
                res[0] = p
        self.add_handler(h)
        while res[0] is None:
            self.recv_packet()
        self.remove_handler(h)
        return res[0]

    # specific BLE commands
    def scan(self, target_uuid, target_address):
        # stop scanning and terminate previous connection 0, 1 and 2
        self.send_command(6, 4)
        for connection_number in range(3):
            self.send_command(3, 0, struct.pack('<B', connection_number))

        # start scanning
        print('scanning...')
        self.send_command(6, 2, b'\x01')
        while True:
            packet = self.recv_packet()
            if packet.payload.endswith(bytes.fromhex(target_uuid)):
                address = list(list(packet.payload[2:8]))
                address_string = ':'.join(format(item, '02x') for item in reversed(address))
                print('found a Myo armband (MAC address: {0})'.format(address_string))
                if target_address is None or target_address.lower() == address_string:
                    # stop scanning and return the found mac address
                    self.send_command(6, 4)
                    print('selected {0}'.format(address_string))
                    return address_string

    def connect(self, target_address):
        # connect to the Myo armband
        address = [int(item, 16) for item in reversed(target_address.split(':'))]
        conn_pkt = self.send_command(6, 3, struct.pack('<6sBHHHH', bytes(address), 0, 6, 6, 64, 0))
        self.conn = list(conn_pkt.payload)[-1]
        self.wait_event(3, 0)

    def get_connections(self):
        return self.send_command(0, 6)

    def disconnect(self):
        if self.conn is not None:
            return self.send_command(3, 0, struct.pack('<B', self.conn))
        return None

    def read_attr(self, attr):
        if self.conn is not None:
            self.send_command(4, 4, struct.pack('<BH', self.conn, attr))
            ble_payload = self.wait_event(4, 5).payload
            # strip off the 4 byte L2CAP header and the payload length byte of the ble payload field
            return ble_payload[5:]
        return None

    def write_attr(self, attr, val):
        if self.conn is not None:
            self.send_command(4, 5, struct.pack('<BHB', self.conn, attr, len(val)) + val)
            ble_payload = self.wait_event(4, 1).payload
            # strip off the 4 byte L2CAP header and the payload length byte of the ble payload field
            return ble_payload[5:]
        return None

    def send_command(self, cls, cmd, payload=b''):
        s = struct.pack('<4B', 0, len(payload), cls, cmd) + payload
        self.ser.write(s)

        while True:
            p = self.recv_packet()
            # no timeout, so p won't be None
            if p.typ == 0:
                return p
            # not a response: must be an event
            self.handle_event(p)