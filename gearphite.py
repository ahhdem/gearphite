#!/usr/bin/env /usr/bin/python
# gearphite.py
# Copyright (C) 2012, Karsten McMinn, Adam Backer
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See
# http://www.gnu.org/licenses/gpl-2.0.html for more details
"""
    ugly yet effective tool for pushing
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
import gearman
import base64
from Crypto.Cipher import AES

# log levels
logLevels = {
                'critical': logging.CRITICAL,
                'error': logging.ERROR,
                'warning': logging.WARNING,
                'info': logging.INFO,
                'debug': logging.DEBUG,
            }

sock = socket.socket()
lasttime = time.time()
hostname = socket.gethostname()
gcounter = 0


parser = optparse.OptionParser()
parser.add_option('-c', '--config', help='full path to the config file')
parser.add_option('-l', '--logging-level',
    help='set log level (critical,error,warning,info, debug')
parser.add_option('-m', '--more-metrics', action="store_true",
    help='enable printing of each sent metric, one per line')
parser.add_option('-s', '--gearman-server',
    help='specify a gearman server to connect to [format HOST:PORT]')
parser.add_option('-g', '--counter', action="store_true",
    help='enable gearphite mps counter')
(options, args) = parser.parse_args()


if options.config:
    execfile(str(options.config))
else:
    print "No config specified, trying default: /etc/gearphite.conf"
    execfile(str('/etc/gearphite.conf'))

log = logging.getLogger('log')
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
    gearman_server = [options.gearman_server]

if options.counter:
    counter = 1


def connect_tsd():
    global sock
    global tsd_server
    global tsd_port
    """
        Connects to  a OpenTSDB TSD daemon
    """
    log.debug("trying to connect to tsd with hostname: " \
        + str(tsd_server) + " and port: " + str(tsd_port))
    sock = socket.socket()
    sock.connect((tsd_server, tsd_port))
    log.info("TSD service connected successfully at: "
        + tsd_server + ":" + str(tsd_port))


def test_tsd():
    global sock

    try:
        peer = sock.getpeername()
    except socket.error:
        return False
    else:
        return True


def close_tsd():
    global sock
    try:
        sock.close()
    except Exception, e:
        log.debug("exception closing socket: " + str(e))


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
        return False

    try:
        sock.sendall(message)
        log.debug("sending to opentsdb: %s" % message)
        return True
    except socket.error, e:
        log.critical("Can't send message to opentsdb error:%s" % (e))
        close_tsd()
        try:
            log.debug("Attempting to reconnect tsd")
            connect_tsd()
        except socket.error, e:
            log.debug("Could not reconnect tsd, sleeping once: " \
                + str(e))
            time.sleep(sleep_time)
            return False
        else:
            log.info("TSD Service reconnected")
            return True


def process_data_file(file_name, delete_after=0):
    """
        processes a file loaded with nagios perf data, and send to a
        a tsd server
    """
    global tsd_server
    global hostname
    tsd_lines = []

    tags = ['metricsource=' + hostname]

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

        tags.append('host=' + str(host))

        if command:
            tags.append('command=' + command)

        log.debug("serviceperfdata=" + service_perf_data)
        try:
            tsd_lines.extend(
                process_perfdata_tsd(service_perf_data, time, tags)
            )
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
                log.warning("Problem sending metric to: "
                    + str(tsd_server))
        else:
            log.debug("No perfdata found in this iteration")


def scrub_perfdata(perfdata):
    """
    sort the perf data
    """
    global badchars
    if not (len(perfdata) > 0):
        log.warning("empty string coming from the gearman queue")
        return

    if not '=' in ''.join(perfdata):
        log.warning('No perfdata found in string value..' + perfdata)
        return

    for elem in perfdata:
        log.debug('Working on item: ' + str(elem))

        if 'HOSTNAME::' in elem:
            host = elem.split('::')[1]
            if len(host) < 2:
                log.warning('something wrong with hostname: ' + str(host))
                return

        if 'PERFDATA' in elem and 'DATATYPE' not in elem:
            service_perf_data = elem.split('::')[1]
            if '/' in service_perf_data:
                service_perf_data = service_perf_data.replace('/', '_')

        if 'CHECKCOMMAND::' in elem:
            command = elem.split('::')[1]
            command = command.translate(None, badchars)

        if 'TIMET::' in elem:
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

        log.debug('succesfully sorted perfdata '
            ' host=' + str(host) + ' command=' + str(command)
            + ' time=' + str(time) + ' service_perf_data='
            + str(service_perf_data))
        return (host, command, time, service_perf_data)


def gearphite_perf(metrics):
    global lasttime
    global gcounter
    global hostname

    second = lasttime + 1
    now = time.time()

    if now >= second:
        xtime = str(now).split('.')[0]
        gmsg = 'mps ' + xtime + ' ' + str(gcounter) + ' metricsource=' \
            + hostname + ' host=' + hostname + ' command=gearphite'
        gcounter = 0
        lasttime = time.time()
        return gmsg
    else:
        gcounter = gcounter + metrics


def process_service_data_gearman(perfdata):
    """
        callback that parses monitoring data from gearman queue
        and sends off to a server
    """
    global tsd_server
    global gearman_server
    global worker_id
    global options
    global counter

    server = gearman_server[0].split(':')[0]
    tsd_lines = []
    tags = ['metricsource=' + server]

    host, command, time, service_perf_data = scrub_perfdata(perfdata)

    tags.append('host=' + str(host))

    if command:
        tags.append('command=' + command)

    log.debug("serviceperfdata=" + service_perf_data)
    try:
        tsd_lines.extend(process_perfdata_tsd(service_perf_data, time, tags))
    except Exception, e:
        log.warning("Error building tsd list: " + str(e))
        return

    log.debug('tsd_lines=' + str(tsd_lines))
    num = len(tsd_lines)

    if counter:
        log.debug("counter enabled sending stats")
        gline = gearphite_perf(num)
        if gline is not None:
            tsd_lines.append(gline)
            num = len(tsd_lines)

    if num > 0:
        if send_tsd(tsd_lines):
            log.debug("OK sent %d metrics to tsd" % num)
            if options.more_metrics:
                for item in tsd_lines:
                    print item

        else:
            log.warning("Problem sending metric to: " + str(tsd_server))
    else:
        log.debug("No perfdata found in this iteration")


def process_perf_string(nagios_perf_string):
    """
        splits out the values and metric names based on an '='
        remove extra characters from values
    """

    global badchars
    log.debug(nagios_perf_string)
    tmp = re.findall("=?[^;]*", nagios_perf_string)
    (name, value) = tmp[0].split('=')
    value = re.sub('[a-zA-Z%]', '', value)
    name = name.translate(None, badchars)
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

        if '=' not in perf:
            continue
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
    r = 'Job() - %s %s %s %s %s %s %s %s' % \
        (d[0], d[1], d[2], d[3], d[4], d[5], d[6], d[7])

    log.debug("RAW DATA")
    log.debug(d)
    log.debug("END RAW")
    if d[0].endswith("PERFDATA"):
        process_service_data_gearman(d)

    return r


def process_gearman_queue(directory):
    """
        setup decrypt cipher - processes the perfdata
        info from the gearman queue - run callback
    """
    log.info("Using gearman queue as perfdata source")

    global secretkey

    # the block size for the cipher object; must be 16, 24, or 32 for AES
    blocksize = 16

    # maximum/minimum key string size
    maxsize = 32

    # bring keystring to the right size. If it's too short, fill with \x0
    if (len(secretkey) < maxsize):
        mod = maxsize - len(secretkey) % maxsize
        for i in range(mod):
            secretkey = secretkey + chr(0)
    elif (len(secretkey) > maxsize):
        secretkey = secretkey[0:maxsize]

    # the character used for padding--with a block cipher such as AES,
    # the value you encrypt must be a multiple of blocksize
    # in length.  This character is used to ensure that your
    # value is always a multiple of blocksize
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

    log.info("Starting gearman worker on " + str(worker_id)
        + " at " + str(gearman_server))

    gm_worker.register_task('perfdata', task_listener_perfdata)

    # Enter our work loop and call gm_worker.after_poll()
    # after each time we timeout/see socket activity
    gm_worker.work()


def main():

    workers = {0: process_spool_dir, 1: process_gearman_queue}

    log.info("Gearphite starting up")

    while True:

        try:
            if not test_tsd():
                connect_tsd()

        except socket.error, e:
            log.error("Can't connect to TSD Service: %s:%s %s" % (tsd_server,
                tsd_port, e))
            log.info("sleeping for: " + str(sleep_time) + " seconds")
            time.sleep(sleep_time)
            continue

        try:
            workers[perfdata_source](spool_directory)

        except Exception, e:
            log.error("Problem starting spool or gearman: " + str(e))
            log.info("Sleeping for: " + str(sleep_time) + " seconds")
            time.sleep(sleep_time)
            continue

        time.sleep(sleep_time)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        log.warning("ctrl-c pressed. Exiting gearphite.")
        sys.exit(1)
