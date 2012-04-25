# Introduction

Gearphite is a fork of Graphios to support processing of nagios performance data from a mod_gearman queue or nagios spool directory.

Instead of sending to graphite, it sends to a opentsdb daemon.

# Requirements

* A working nagios / icinga server
* A working opentsdb install and running tsd daemon
* Python 2.4 or later, 2.6 reccomended
* working mod_gearman setup, with perfdata=yes

# License

Gearphite/Graphios is release under the [GPL v2](http://www.gnu.org/licenses/gpl-2.0.html).

# Documentation

The goal of this tool is to get nagios perf data into opentsdb.

The format is simply::

    put metricname timestamp value tag1=value tag2=value

What the perfdata is, depends on what perfdata your nagios plugin provides.

Opentsdb needs tags to be effective and gearphite adds some basic ones. '/'s are converted to '_'.

Example 1
--------------

If your check was spitting these metrics into the perfdata::

    rta=4.029ms;10.000;30.000;0; pl=0%;5;10;; rtmax=4.996ms;;;; rtmin=3.066ms;;;;

Gearphite would then send the following to opentsdb::

    put rta 1333783979 4.029 host=myhost metricsource=gearman_server command=check_command
    put pl 1333783979 4.029 host=myhost metricsource=gearman_server command=check_command
    put rtmax 1333783979 4.029 host=myhost metricsource=gearman_server command=check_command
    put rtmin 1333783979 4.029 host=myhost metricsource=gearman_server command=check_command

The time used is nagios:timet, seconds from epoch time when the plugin results were received.

Whatever value is on the left side of the equals sign will become the metric name.

Example 2
---------------

We have a load plugin that provides the following perfdata::

    load1=8.41;20;22;; load5=6.06;18;20;; load15=5.58;16;18

Would give the following:

    put load1 1333783979 4.029 host=myhost metricsource=gearman_server command=check_command
    put load5 1333783979 4.029 host=myhost metricsource=gearman_server command=check_command
    put load15 1333783979 4.029 host=myhost metricsource=gearman_server command=check_command



Testing
---------------

Gearphite perfdata from spool directory has not been tested. Gearman queue perfdata however has been tested thorougyly and is in production.


Performance
-----------
On a busy c1.xlarge ec2 instance It delivers about a max of 2000 metrics a second to opentsdb. This could be improved with less string and regex operations. To get more than than you can run multiple daemons.


# Installation


Setting this up on the nagios front is very much like pnp4nagios with npcd. (You do not need to have any pnp4nagios experience at all). If you are already running pnp4nagios , check out my pnp4nagios notes (below).

Steps:

(1) nagios/gearman
--------------

See: https://github.com/shawn-sterling/graphios/blob/master/README.md for details about configuring nagios spool directory. Whether you are using the spool directory or gearman, this script basically is needs a string with the word PERFDATA in it with values separated by whitespace. Other things like the command, host and time are scrubbed out. The expected format is a tab delimited string like this::

    DATATYPE::SERVICEPERFDATA TIMET::1335379911 HOSTNAME::my-server-01 SERVICEDESC::CPU load SERVICEPERFDATA::load1=0;20;40;0; load5=0.01;20;40;0; load15=0.02;20;40;0; SERVICECHECKCOMMAND::check_mk-cpu.loads SERVICESTATE::0 SERVICESTATETYPE::1\n\n\n\x00\x00\x00\x00\x00\x00\x00

(3) gearphite.py
---------------

It doesn't matter where gearphite.py lives, I put it in ~nagios/bin . We put ours in path. The util/gearphite.init wants it int /usr/bin/.

The gearphite.py can run as whatever user you want, as long as you have access to the spool directory/gearman, log file.

Gearphite has a few options on the command line as well as a interpreted config::

    usage: gearphite.py [options]

    options:
      -h, --help            show this help message and exit
      -c CONFIG, --config=CONFIG
                            full path to the config file
      -l LOGGING_LEVEL, --logging-level=LOGGING_LEVEL
                            set log level (critical,error,warning,info, debug
      -m, --more-metrics    enable printing of each sent metric, one per line
      -s GEARMAN_SERVER, --gearman-server=GEARMAN_SERVER
                            specify a gearman server to connect to [format
                            HOST:PORT]
      -g, --counter         enable gearphite mps counter


To configure gearphite, set the values in the config file as appropiate for your installation of nagios/gearman, or run it from the command line overriding defaults in the config file such as the sample init.d script does.

See the sample config in util/gearphite.conf.example for details on configuration directives.


(4) Sample Install
----------------------------------
Here's a quick install for a centos/rhel distro::

    git clone git://github.com/kmcminn/gearphite.git
    cp gearphite/util/gearphite.init /etc/init.d/gearphite
    cp gearphite/util/gearphite.logrotate /etc/logrotate.d
    cp gearphite/util/gearphite.conf.example /etc/gearphite.conf
    install gearphite/gearphite.py /usr/bin/gearphite.py
    chown root:root /etc/init.d/gearphite
    pip install gearman pycrypto

    * edit /etc/gearphite.conf to your liking
    * edit /etc/init.d/gearphite to your liking

    chkconfig add gearphite
    chkconfig gearphite on
    service gearphite start

# About

Goal was to get a simple script working. There are many ways it could be improved (twisted, threads/multiprocess, internal log rotation, consolidate with other projects like bucky or graphios, add more statistics, etc). Go for it! Pull reqs welcome. 
