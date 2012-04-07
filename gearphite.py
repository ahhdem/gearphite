#!/usr/bin/env /usr/bin/python 
"""
    gearphite - gearman perfdata ripper
    copyright 2012, Adam Backer, Karsten McMinn

    Ugly yet effective daemon script for pushing
    data into opentsdb from nagios.
"""

import os
import optparse
import sys
import re
import logging
import logging.handlers
import time
import socket
import cPickle as pickle
import struct

import gearman, base64
from Crypto.Cipher import AES

# log levels
logLevels = {
                'critical': logging.CRITICAL,
                'error': logging.ERROR,
                'warning': logging.WARNING,
                'info': logging.INFO,
                'debug': logging.DEBUG,
            }


# opentsdb tsd server name
tsd_server = 'graph.dev.internal.playfish.com'

# opentsdb tsd server port 
tsd_port = 8081

# hostname:port of where the gearman queue is
gearman_server = [ 'dev-mon-nag02m:4730' ]

# worker id 
worker_id = 'perfdata_'+socket.gethostname()

# nagios spool directory
spool_directory = '/var/spool/nagios/gearphite'

#use nagios spool directory or gearman (0:spool or 1:gearman) -- addition, not from PoC
perfdata_source = 1 

# gearphite log locatoin
log_max_size = 25165824         # 24 MB
log_file = '/mnt/logs/icinga/gearphite.log'

# uncomment to override setting log level on command line
log_level = 'info'

# How long to sleep between processing the spool directory
sleep_time = 15

# when we can't connect to opentsdb, the sleeptime is doubled until we hit max
sleep_max = 30

#set secret key  
secretkey = 'pfg342m4n'


parser = optparse.OptionParser()
parser.add_option('-l', '--logging-level', help='set log level (critical,error,warning,info, debug) \
    default set to: ' +str(log_level))
parser.add_option('-m', '--more-metrics', action="store_true", help='enable printing of ' 
    + 'each sent metric, one per line')
parser.add_option('-s', '--gearman-server', help='specify a gearman server to connect to'
    + ' [format HOST:PORT]')
(options, args) = parser.parse_args()

sock = socket.socket()


# log not available to all threads if defined in main(), cheap hack
log = logging.getLogger('log')
log_handler = logging.handlers.RotatingFileHandler(log_file,
    maxBytes=log_max_size, backupCount=4)
f = logging.Formatter("%(asctime)s %(filename)s %(levelname)s %(message)s",
    "%B %d %H:%M:%S")

if options.logging_level:
    logging_level = logLevels.get(options.logging_level)
    console = logging.StreamHandler()
    log.setLevel(logging_level)
    console.setFormatter(f)
    log.addHandler(console)
else:
    logging_level = logLevels.get(log_level)
    console = logging.StreamHandler()
    log.setLevel(logging_level)
    console.setFormatter(f)
    log.addHandler(console)

if options.gearman_server:
    gearman_server = [ options.gearman_server ]


def connect_tsd():
    """
        Connects to  a OpenTSDB TSD daemon 
    """
    global sock
    sock = socket.socket()
    try:
        sock.connect((tsd_server, tsd_port))
        return True
    except Exception, e:
        log.warning("Can't connect to TSD Service: %s:%s %s" % (tsd_server,
            tsd_port, e))
        return False

def send_tsd(output):
    """
        Sends a formatted list of data to opentsdb
        every line will need to have a \n before doing send_all
    """
    global sock
    global sleep_time
    message = ''
    for elei in output:
        line = 'put ' + elei
        message += line + '\n'

    if not message:
        log.debug("tsd message empty, not sending")
        return

    try:
        sock.sendall(message)
        log.debug("sending to opentsdb: %s" % message)
        return True
    except Exception, e:
        log.critical("Can't send message to opentsdb error:%s" % (e))
        while True:
            sock.close()
            if connect_tsd():
                sleep_time = 15     # reset sleep_time to 15
                return False
            else:
                if sleep_time < sleep_max:
                    sleep_time = sleep_time + sleep_time
                    log.warning("TSD Service not responding. Increasing " + \
                        "sleep_time to %s." % (sleep_time))
                else:
                    log.warning("TSD Service not responding. Sleeping %s" % \
                        (sleep_time))
            log.debug("sleeping %s" % (sleep_time))
            time.sleep(sleep_time)
        return False



def process_data_file(file_name, delete_after=0):
    """
        processes a file loaded with nagios perf data, and send to a
        a tsd server
    """
    tsd_lines = []

    try:
        f = open(file_name, "r")
        file_array = f.readlines()
        f.close
    except Exception, e:
        log.critical("Can't open file:%s error: %s" % (file_name, e))
        sys.exit(2)

    for line in file_array:
        variables = line.split('\t')

        host, command, time, service_perf_data = scrub_perfdata(perfdata)


        tags.append('host='+str(host))

        if command:
            tags.append('command='+command)

        log.debug("serviceperfdata="+service_perf_data)
        try:
            tsd_lines.extend(process_perfdata_tsd(service_perf_data, time, tags))
        except Exception, e:
            log.warning("Error building tsd list: " + str(e))
            return

        log.debug('tsd_lines=' + str(tsd_lines))
        if len(tsd_lines) > 0:
            if send_tsd(tsd_lines):
                log.debug("OK sent %d metrics to tsd" % len(tsd_lines))
                if options.more_metrics:
                    for item in tsd_lines:
                        print item

                if delete_after:
                    log.debug("removing file, %s" % (file_name))
                    try:
                        os.remove(file_name)
                    except Exception, e:
                        log.critical("couldn't remove file %s error:%s" % (
                            file_name, e))
            else:
                log.warning("Problem sending metric to: " + str(gearman_server[0]))
        else:
                log.debug("No perfdata found in this iteration")
        return

def scrub_perfdata(perfdata):

    if not (len(perfdata) > 0):
        log.warning("empty string coming from the gearman queue")
        return
    if not '=' in ''.join(perfdata):
        log.warning('No perfdata found in string value..' + perfdata)
        return

    for elem in perfdata:
        log.debug('Working on item: ' + str(elem))

        if 'HOSTNAME' in elem:
            host = elem.split('::')[1]
            if len(host) < 2:
                log.warning('something wrong with hostname: ' + str(host))
                return

        if 'PERFDATA' in elem and 'DATATYPE' not in elem:
            service_perf_data = elem.split('::')[1]
            if '/' in service_perf_data:
                service_perf_data = service_perf_data.replace('/', '_')

        if 'CHECKCOMMAND' in elem:
            command = elem.split('::')[1]


        if 'TIMET' in elem:
            time = elem.split('::')[1]
    
    if not command:
        command = 'null'

    if not host or not command or not time or not service_perf_data:
        log.debug('problem with perfdata '
            ' host=' + str(host) + ' command=' + str(command)
            + ' time=' + str(time) + ' service_perf_data='
            + str(service_perf_data))
        return
    else:
        return ( host, command, time, service_perf_data )


def process_service_data_gearman(perfdata):
    """
        callback that parses monitoring data from gearman queue
        and sends off to a server
    """
    global geaman_server
    global options
    server = gearman_server[0].split(':')[0]
    tsd_lines = []
    tags = [ 'metricsource='+server ]

    host, command, time, service_perf_data = scrub_perfdata(perfdata)
    
    tags.append('host='+str(host))

    if command:
        tags.append('command='+command)

    log.debug("serviceperfdata="+service_perf_data)
    try:
        tsd_lines.extend(process_perfdata_tsd(service_perf_data, time, tags))
    except Exception, e:
        log.warning("Error building tsd list: " + str(e))
        return

    log.debug('tsd_lines=' + str(tsd_lines))
    if len(tsd_lines) > 0:
        if send_tsd(tsd_lines):
            log.debug("OK sent %d metrics to tsd" % len(tsd_lines))
            if options.more_metrics:
                for item in tsd_lines:
                    print item
        else:
            log.warning("Problem sending metric to: " + str(gearman_server[0]))
    else: 
            log.debug("No perfdata found in this iteration") 
    return


def process_perf_string(nagios_perf_string):
    """
        splits out the values and metric names based on an '='
        test for an '=' before calling or test for ValueError
    """

    tmp = re.findall("=?[^;]*", nagios_perf_string)
    (name, value) = tmp[0].split('=')
    value = re.sub('[a-zA-Z]', '', value)
    value = re.sub('\%', '', value)

    return name, value


def process_perfdata_tsd(perf_data, time, tags):
    """
        loops perfdata and builds a list of result
    """
    tsd_lines = []
    perf_list = perf_data.split(" ")

    if '=' not in perf_data:
        return tsd_lines

    for perf in perf_list:

        (name, value) = process_perf_string(perf)
        new_line = "%s %s %s %s" % (name, time, value, ' '.join(tags))
        log.debug("new line = %s" % (new_line))
        tsd_lines.append(new_line)

    return tsd_lines


def process_spool_dir(directory):
    """
        processes the files in the spool directory
    """
    log.info("Using spool dir as performance data source")
    file_list = os.listdir(directory)
    for file in file_list:
        if file == "host-perfdata" or file == "service-perfdata":
            continue
        file_dir = os.path.join(directory, file)
        process_data_file(file_dir, 1)

def task_listener_perfdata(gearman_worker, gearman_job):
    """
    the gearma worker callback function
    """
    decrypted = DecodeAES(cipher, gearman_job.data)

    # make array of data split on tab, for use -in this function-
    d = decrypted.split('\t')
    r = 'Job() - %s %s %s %s %s %s %s %s' % (d[0],d[1],d[2],d[3],d[4],d[5],d[6],d[7])

    if d[0].endswith("PERFDATA"):
        process_service_data_gearman(d)

    return r


def process_gearman_queue(directory):
    """
        setup decrypt cipher - processes the perfdata info from the gearman queue - run callback
    """
    log.info("Using gearman queue as perfdata source")
    
    global secretkey

    # the block size for the cipher object; must be 16, 24, or 32 for AES
    blocksize = 16

    # maximum/minimum key string size
    maxsize = 32

    # bring keystring to the right size. If it's too short, fill with \x0
    if (len(secretkey) < maxsize):
        mod = maxsize - len(secretkey)%maxsize
        for i in range(mod):
            secretkey = secretkey + chr(0)
    elif (len(secretkey) > maxsize):
        secretkey = secretkey[0:maxsize]

    # the character used for padding--with a block cipher such as AES, the value
    # you encrypt must be a multiple of blocksize in length.  This character is
    # used to ensure that your value is always a multiple of blocksize
    padding = '{'

    # one-liner to sufficiently pad the text to be encrypted
    pad = lambda s: s + (blocksize - len(s) % blocksize) * padding

    # one-liners to encrypt/encode and decrypt/decode a string
    # encrypt with AES, encode with base64
    EncodeAES = lambda c, s: base64.b64encode(c.encrypt(pad(s)))
    global DecodeAES
    DecodeAES = lambda c, e: c.decrypt(base64.b64decode(e)).rstrip(padding)

    # create a cipher object using the secret
    global cipher 
    cipher = AES.new(secretkey)

    # from python-gearaman docs..
    gm_worker = gearman.GearmanWorker(gearman_server)

    # gm_worker.set_client_id is optional
    gm_worker.set_client_id(worker_id)

    log.info("Starting gearman perfdata worker on " + str(worker_id)
        + " connecting to gearman queue at " + str(gearman_server))

    gm_worker.register_task('perfdata', task_listener_perfdata)


    # Enter our work loop and call gm_worker.after_poll() after each time we timeout/see socket activity
    gm_worker.work()


def main():

    # see perfdata_source config value
    workers =   {
                    0 : process_spool_dir, 
                    1 : process_gearman_queue,
                }
    global sock
    log.info("Gearphite starting up")
    try:
        connect_tsd()
        while True:
            workers[perfdata_source](spool_directory)
            time.sleep(sleep_time) # only affects spool directory parsing
    except KeyboardInterrupt:
        log.info("ctrl-c pressed. Exiting gearphite.")


if __name__ == '__main__':
    main()

