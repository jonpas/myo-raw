#
# Copyright (c) 2017 - 2018 Matthias Gazzari
#
# Licensed under the MIT license. See the LICENSE file for details.
#

'''A Python library to communicate with the Thalmic Myo'''

from setuptools import setup

def readme():
    with open('README.rst') as f:
        return f.read()

setup(
    name='myo_raw',
    use_scm_version=True,
    setup_requires=['setuptools_scm'],
    description=__doc__,
    long_description=readme(),
    author='Danny Zhu, Alvaro Villoslada, Fernando Cosentino',
    maintainer='Matthias Gazzari',
    maintainer_email='matthias.gazzari@stud.tu-darmstadt.de',
    url='https://github.com/qtux/myo-raw',
    license='MIT',
    packages=['myo_raw',],
    install_requires=['pyserial>=3.4',],
    python_requires='>=3.3',
    extras_require={
        'emg':['pygame>=1.9.3',],
        'classification':['numpy>=1.13.3', 'pygame>=1.9.3', 'scikit-learn>=0.19.1',],
    },
    keywords='thalmic myo EMG electromyography IMU inertial measurement unit',
    platforms='any',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: MIT License',
        'Intended Audience :: Science/Research',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
