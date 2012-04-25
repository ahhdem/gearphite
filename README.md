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

(1) nagios.cfg
--------------

Your nagios.cfg is going to need to modified to send the graphite data to the perfdata files.

<pre>
service_perfdata_file=/var/spool/nagios/gearphite/service-perfdata
service_perfdata_file_template=DATATYPE::SERVICEPERFDATA\tTIMET::$TIMET$\tHOSTNAME::$HOSTNAME$\tSERVICEDESC::$SERVICEDESC$\tSERVICEPERFDATA::$SERVICEPERFDATA$\tSERVICECHECKCOMMAND::$SERVICECHECKCOMMAND$\tHOSTSTATE::$HOSTSTATE$\tHOSTSTATETYPE::$HOSTSTATETYPE$\tSERVICESTATE::$SERVICESTATE$\tSERVICESTATETYPE::$SERVICESTATETYPE$\tGRAPHITEPREFIX::$_SERVICEGRAPHITEPREFIX$\tGRAPHITEPOSTFIX::$_SERVICEGRAPHITEPOSTFIX$

service_perfdata_file_mode=a
service_perfdata_file_processing_interval=15
service_perfdata_file_processing_command=graphite_perf_service

host_perfdata_file=/var/spool/nagios/gearphite/host-perfdata
host_perfdata_file_template=DATATYPE::HOSTPERFDATA\tTIMET::$TIMET$\tHOSTNAME::$HOSTNAME$\tHOSTPERFDATA::$HOSTPERFDATA$\tHOSTCHECKCOMMAND::$HOSTCHECKCOMMAND$\tHOSTSTATE::$HOSTSTATE$\tHOSTSTATETYPE::$HOSTSTATETYPE$\tGRAPHITEPREFIX::$_HOSTGRAPHITEPREFIX$\tGRAPHITEPOSTFIX::$_HOSTGRAPHITEPOSTFIX$

host_perfdata_file_mode=a
host_perfdata_file_processing_interval=15
host_perfdata_file_processing_command=graphite_perf_host
</pre>

Which sets up some custom variables, specifically:
for services:
$\_SERVICEGRAPHITEPREFIX
$\_SERVICEGRAPHITEPOSTFIX

for hosts:
$\_HOSTGRAPHITEPREFIX
$\_HOSTGRAPHITEPOSTFIX

The prepended HOST and SERVICE is just the way nagios works, \_HOSTGRAPHITEPREFIX means it's the \_GRAPHITEPREFIX variable from host configuration.

(2) nagios commands
-------------------

There are 2 commands we setup in the nagios.cfg:

graphite\_perf\_service
graphite\_perf\_host

Which we now need to define:

I use include dirs, so I make a new file called gearphite\_commands.cfg inside my include dir. Do that, or add the below commands to one of your existing nagios config files.

#### NOTE: Your spool directory may be different, this is setup in step (1) the service_perfdata_file, and host_perfdata_file.

<pre>
define command {
    command_name            graphite_perf_host
    command_line            /bin/mv /var/spool/nagios/gearphite/host-perfdata /var/spool/nagios/gearphite/host-perfdata.$TIMET$

}

define command {
    command_name            graphite_perf_service
    command_line            /bin/mv /var/spool/nagios/gearphite/service-perfdata /var/spool/nagios/gearphite/service-perfdata.$TIMET$
}
</pre>

All these commands do is move the current files to a different filename that we can process without interrupting nagios. This way nagios doesn't have to sit around waiting for us to process the results.


(3) gearphite.py
---------------

It doesn't matter where gearphite.py lives, I put it in ~nagios/bin . We put ours in path.

The gearphite.py can run as whatever user you want, as long as you have access to the spool directory/gearman, log file.

The config for gearphite.py is in the script itself. Maybe we'll throw in ConfigPaser and break out
the config in the future.

#### NOTE: You WILL need to edit this script and change a few variables, they are right near the top and commented in the script. Here they are in case you are blind:

<pre>
############################################################
##### You will likely need to change some of the below #####

# tsd hostname
tsd_server = 'graph.tsd.server.foo'

# tsd daemon port, user defined, we use 8081
tsd_port = 8081

# nagios spool directory
spool_directory = '/var/spool/nagios/gearphite'

# hostname:port of where the gearman queue is can also be specified with -s
gearman_server = [ 'dev-mon-nag02m:4730' ]

# gearman worker id
worker_id = 'perfdata_'+socket.gethostname()

#use nagios spool directory or gearman (0:spool or 1:gearman)
perfdata_source = 1

# gearphite log locatoin
log_max_size = 25165824         # 24 MB
log_file = '/var/log/gearphite.log'

# log_level to write to the log file, info or warning recommended for production
log_level = 'info'

# How long to sleep between processing the spool/queue when a connection is lost to tsd
sleep_time = 15

# when we can't connect to opentsdb, the sleeptime is doubled until we hit max
sleep_max = 60

#set gearman secret key  
secretkey = 'SUPERKEY'

##############################################################################
</pre>



(4) Optional init script: gearphite
----------------------------------

cp gearphite.init /etc/init.d/gearphite
chown root:root /etc/init.d/gearphite
chmod 750 /etc/init.d/gearphite

#### NOTE: You may need to change the location and username that the script runs as. this slightly depending on where you decided to put gearphite.py

The lines you will likely have to change:
<pre>
prog="/opt/nagios/bin/gearphite.py"
GRAPHIOS_USER="nagios"
</pre>

(5) Your host and service configs
---------------------------------

Once you have done the above you need to add a custom variable to the hosts and services that you want sent to graphite.

The format that will be sent to carbon is:

<pre>
_graphiteprefix.hostname._graphitepostfix.perfdata
</pre>

You do not need to set both graphiteprefix and graphitepostfix. Just one or the other will do. If you do not set at least one of them, the data will not be sent to graphite at all.

Examples:

<pre>
define host {
    name                        myhost
    check_command               check_host_alive
    _graphiteprefix             monitoring.nagios01.pingto
}
</pre>

Which would create the following graphite entries with data from the check\_host\_alive plugin:

    monitoring.nagios01.pingto.myhost.rta
    monitoring.nagios01.pingto.myhost.rtmin
    monitoring.nagios01.pingto.myhost.rtmax
    monitoring.nagios01.pingto.myhost.pl

<pre>
define service {
    service_description         MySQL threads connected
    host_name                   myhost
    check_command               check_mysql_health_threshold!threads-connected!3306!1600!1800
    _graphiteprefix             monitoring.nagios01.mysql
}
</pre>

Which gives me:

    monitoring.nagios01.mysql.myhost.threads_connected

See the Documentation (above) for more explanation on how this works.



# PNP4Nagios Notes:

Are you already running pnp4nagios? And want to just try this out and see if you like it? Cool! This is very easy to do without breaking your PNP4Nagios configuration (but do a backup just in case).

Steps:

(1) In your nagios.cfg:
-----------------------

Add the following at the end of your:

<pre>
host_perfdata_file_template
\tGRAPHITEPREFIX::$_HOSTGRAPHITEPREFIX$\tGRAPHITEPOSTFIX::$_HOSTGRAPHITEPOSTFIX$

service_perfdata_file_template
\tGRAPHITEPREFIX::$_SERVICEGRAPHITEPREFIX$\tGRAPHITEPOSTFIX::$_SERVICEGRAPHITEPOSTFIX$
</pre>

This will add the variables to your check results, and will be ignored by pnp4nagios.

(2) Change your commands:
-------------------------

(find your command names under host\_perfdata\_file\_processing\_command and service\_perfdata\_file\_processing\_command in your nagios.cfg)

You likely have 2 commands setup that look something like these two:

<pre>
define command{
       command_name    process-service-perfdata-file
       command_line    /bin/mv /usr/local/pnp4nagios/var/service-perfdata /usr/local/pnp4nagios/var/spool/service-perfdata.$TIMET$
}

define command{
       command_name    process-host-perfdata-file
       command_line    /bin/mv /usr/local/pnp4nagios/var/host-perfdata /usr/local/pnp4nagios/var/spool/host-perfdata.$TIMET$
}
</pre>

Instead of just moving the file; move it then copy it, then we can point gearphite at the copy.

You can do this by either:

(1) Change the command\_line to something like:

<pre>
command_line    "/bin/mv /usr/local/pnp4nagios/var/host-perfdata /usr/local/pnp4nagios/var/spool/host-perfdata.$TIMET$ && cp /usr/local/pnp4nagios/var/spool/host-perfdata.$TIMET$ /usr/local/pnp4nagios/var/spool/gearphite"
</pre>

OR

(2) Make a script:

<pre>
#!/bin/bash
/bin/mv /usr/local/pnp4nagios/var/host-perfdata /usr/local/pnp4nagios/var/spool/host-perfdata.$TIMET$
cp /usr/local/pnp4nagios/var/spool/host-perfdata.$TIMET$ /usr/local/pnp4nagios/var/spool/gearphite

change the command_line to be:
command_line    /path/to/myscript.sh
</pre>

You should now be able to start at step 3 on the above instructions.


# Trouble getting it working?

I will help the first few people that have problems getting this working, and update the documentation on what is not clear. I am not offering to teach you how to setup Nagios, this is for intermediate+ nagios users. Email me at shawn@systemtemplar.org and I will do what I can to help.

# Got it working?

Cool! Drop me a line and let me know how it goes.

# Find a bug?

Open an Issue on github and I will try to fix it asap.

# Contributing

I'm open to any feedback / patches / suggestions.

I'm still learning python so any python advice would be much appreciated.

Shawn Sterling shawn@systemtemplar.org
