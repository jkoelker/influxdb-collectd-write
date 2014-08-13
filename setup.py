# -*- coding: utf-8 -*-

from setuptools import setup

version = '0.1'

setup(name='influxdb-collectd-write',
      version=version,
      description='Collectd Python plugin for writing to InfluxDB',
      long_description=open('README.rst').read(),
      keywords='',
      author='Jason Kölker',
      author_email='jason@koelker.net',
      url='https://github.com/jkoelker/influxdb-colelctd-write',
      license='MIT',
      py_modules=['write_influxdb'],
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          'influxdb',
          'Monotime',
          'requests',
      ],
      )
