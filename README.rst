An influxdb collectd write plugin
=================================

Usage
=====

Install then add it to collectd.conf (default values shown and may be omitted):

.. code-block:: xml

 <LoadPlugin python>
   Globals true
 </LoadPlugin>

 <Plugin python>
     LogTraces true
     Import "write_influxdb"

     <Module "write_influxdb">
         host "localhost"
         port 8086
         username "root"
         password "root"
         database "collectd"
         ssl false
         verify_ssl false
         use_udp false
         udp_port 4444
         retry false
         buffer false
     </Module>
 </Plugin>


In addition ``timeout`` can be specified as an integer to set the HTTP timeout
for writing to InfluxDB. Additional ``types.db`` files can be specified by
adding one or more ``typesdb`` paramaters to the module config specifying the
path to the file. Write buffering to InfluxDB can be enabled by specifying
``buffer true`` in the config. By default it will flush the buffer every ``1024``
values or ``10`` seconds (whichever happens first). The format to change these
is ``buffer true 2048`` to increase the value buffer or ``buffer true 1024 5``
to change the time buffer.
