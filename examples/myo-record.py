import argparse
import collections
import csv
import time
from datetime import datetime
from pathlib import Path

from myo_raw import MyoRaw

emg_header = ['emg1', 'emg2', 'emg3', 'emg4', 'emg5', 'emg6', 'emg7',
              'emg8', 'moving']

imu_header = ['ori_w', 'ori_x', 'ori_y', 'ori_z', 'accel_1',
              'accel_2', 'accel_3', 'gyro_1', 'gyro_2', 'gyro_3']


class Myo(MyoRaw):

    def __init__(self,  tty=None):
        MyoRaw.__init__(self, tty)


def flatten(l):
    for el in l:
        if isinstance(el, collections.Iterable) and not (
                isinstance(el, (str, bytes))):
            yield from flatten(el)
        else:
            yield el


def write_data(writer, data):
    row = list(flatten(data))
    writer.writerow(row)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--tty", default=None,
                        help="The Myo device")
    parser.add_argument('-o', '--outdir', metavar='path',
                        default='./',
                        help="Directory to write result files.")
    args = parser.parse_args()

    # Make output files.
    now = datetime.fromtimestamp(time.time()).isoformat(timespec='seconds')
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    emg_file = open(str(outdir / (now + '_emg.csv')), 'w', newline='')
    imu_file = open(str(outdir / (now + '_imu.csv')), 'w', newline='')

    emg_writer = csv.writer(emg_file, csv.unix_dialect,
                            quoting=csv.QUOTE_MINIMAL)
    emg_writer.writerow(emg_header)

    imu_writer = csv.writer(imu_file, csv.unix_dialect,
                            quoting=csv.QUOTE_MINIMAL)
    imu_writer.writerow(imu_header)

    m = Myo(args.tty)
    m.add_emg_handler(lambda *args: write_data(emg_writer, args))
    m.add_imu_handler(lambda *args: write_data(imu_writer, args))
    m.connect()

    # Enable never sleep mode.
    m.sleep_mode(1)

    try:
        while True:
            m.run(1)
    except KeyboardInterrupt:
        pass
    finally:
        m.disconnect()
        emg_file.close()
        imu_file.close()
        print()
