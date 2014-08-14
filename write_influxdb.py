# -*- coding: utf-8 -*-

# NOTE(jkoelker) patch time to include monotonic
import monotime  # noqa

import collections
import Queue as queue
import time
import threading
import traceback

import collectd
import influxdb
import requests


def parse_types_file(path):
    """ This function tries to parse a collectd compliant types.db file.
    Basically stolen from collectd-carbon/memsql-collectd.
    """
    data = {}

    f = open(path, 'r')

    for line in f:
        fields = line.split()
        if len(fields) < 2:
            continue

        type_name = fields[0]

        if type_name[0] == '#':
            continue

        v = []
        for ds in fields[1:]:
            ds = ds.rstrip(',')
            ds_fields = ds.split(':')

            if len(ds_fields) != 4:
                continue

            v.append(ds_fields[0])

        data[type_name] = v

    f.close()

    return data


def parse_types(*paths):
    data = {}

    for path in paths:
        try:
            data.update(parse_types_file(path))
        except IOError:
            pass

    return data


def format_identifier(value):
    plugin_name = value.plugin
    type_name = value.type

    if value.plugin_instance:
        plugin_name = '%s-%s' % (plugin_name, value.plugin_instance)

    if value.type_instance:
        type_name = '%s-%s' % (type_name, value.type_instance)

    return '%s/%s/%s' % (value.host, plugin_name, type_name)


def PeriodicTimer(interval, function, *args, **kwargs):
    return _PeriodicTimer(interval, function, args, kwargs)


class _PeriodicTimer(threading._Timer):
    def run(self):
        while not self.finished.is_set():
            self.finished.wait(self.interval)
            if not self.finished.is_set():
                try:
                    self.function(*self.args, **self.kwargs)
                except:
                    collectd.error(traceback.format_exc())


class BulkPriorityQueue(queue.PriorityQueue):
    def put(self, item, *args, **kwargs):
        return queue.PriorityQueue.put(self, (time.monotonic(), item),
                                       *args, **kwargs)

    def get_bulk(self, timeout=-1, size=0, flush=False):
        values = []
        add = values.append

        if timeout < 0:
            timeout = 0

        now = time.monotonic()
        timeout = now - timeout

        self.not_empty.acquire()
        try:
            while self._qsize():
                if (flush or self.queue[0][0] < timeout or
                        self._qsize() > size):
                    add(self._get()[1])

                else:
                    break

            if values:
                self.not_full.notify()

            return values
        finally:
            self.not_empty.release()


class InfluxDB(object):
    def __init__(self):
        self._config = {'host': 'localhost',
                        'port': 8086,
                        'username': 'root',
                        'password': 'root',
                        'database': 'collectd',
                        'ssl': False,
                        'verify_ssl': False,
                        'timeout': None,
                        'use_udp': False,
                        'udp_port': 4444}
        self._client = None
        self._retry = False
        self._buffer = False
        self._buffer_size = 1024
        self._buffer_sec = 10.0
        self._typesdb = ['/usr/share/collectd/types.db']
        self._types = None
        self._queues = None
        self._flush_thread = None

    def _flush(self, timeout=-1, identifier=None, flush=False):
        if not self._buffer:
            flush = True

        if identifier:
            if identifier in self._queues:
                queues = [(identifier, self._queues[identifier])]

            else:
                queues = []

        else:
            queues = self._queues.items()

        if not flush and timeout == -1:
            if sum([q[1].qsize() for q in queues]) < self._buffer_size:
                return

        data = {}
        values = []
        add = values.extend

        for identifier, queue in queues:
            queue_values = queue.get_bulk(timeout=timeout,
                                          flush=flush)

            if not queue_values:
                continue

            data[identifier] = queue_values
            add(queue_values)

        try:
            self._client.write_points(values)

        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError):
            if self._retry:
                for identifier, values in data:
                    for v in values:
                        self._queues[identifier].put(v)

    def config(self, conf):
        for node in conf.children:
            key = node.key.lower()
            values = node.values

            if key in self._config:
                if key in ('ssl', 'verify_ssl', 'use_udp'):
                    self._config[key] = True

                elif key in ('port', 'timeout', 'udp_port'):
                    self._config[key] = int(values[0])

                else:
                    self._config[key] = values[0]

            elif key == 'retry':
                self._retry = True

            elif key == 'buffer':
                self._buffer = values[0]
                num_values = len(values)

                if num_values == 2:
                    self._buffer_size = int(values[1])

                elif num_values == 3:
                    self._buffer_size = int(values[1])
                    self._buffer_sec = float(values[2])

            elif key == 'typesdb':
                self._typesdb.append(values[0])

    def flush(self, timeout=-1, identifier=None):
        self._flush(timeout=timeout, identifier=identifier)

    def init(self):
        self._types = parse_types(*self._typesdb)
        self._client = influxdb.InfluxDBClient(**self._config)
        self._queues = collections.defaultdict(lambda: BulkPriorityQueue())
        self._flush_thread = PeriodicTimer(self._buffer_sec,
                                           self._flush,
                                           flush=True)
        self._flush_thread.start()

    def shutdown(self):
        if self._flush_thread is not None:
            self._flush_thread.cancel()
            self._flush_thread.join()

        self._flush(flush=True)

    def write(self, sample):
        value_types = self._types.get(sample.type)

        if value_types is None:
            msg = 'plugin: %s unknown type %s, not listed in %s'

            collectd.info('write_influxdb: ' + msg % (sample.plugin,
                                                      sample.type,
                                                      self._typesdb))
            return

        identifier = format_identifier(sample)
        columns = ['time']
        columns.extend(value_types)
        columns.extend(('host', 'type'))

        points = [sample.time]
        points.extend(sample.values)
        points.extend((sample.host, sample.type))

        if sample.plugin_instance:
            columns.append('plugin_instance')
            points.append(sample.plugin_instance)

        if sample.type_instance:
            columns.append('type_instance')
            points.append(sample.type_instance)

        data = {'name': sample.plugin,
                'columns': columns,
                'points': [points]}

        self._queues[identifier].put(data)
        self._flush()


db = InfluxDB()
collectd.register_config(db.config)
collectd.register_flush(db.flush)
collectd.register_init(db.init)
collectd.register_shutdown(db.shutdown)
collectd.register_write(db.write)
