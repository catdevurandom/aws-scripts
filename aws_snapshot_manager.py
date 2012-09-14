#!/usr/bin/env python
#
# aws_snapshot_manager.py 
#
# Takes a daily snapshot and manages your archival snapshot inventory.  
#
# Requirements:
# 
# * A working boto configuration for establishing connection to your AWS environment
# * This script is meant to be run once a day with a cron job
# 
# Snapshot management logic is as follows:
#
# * Always keep the past 7 days of snapshots
# * Always keep the snapshot taken on the last day of the month.
#
# To do:
# 
# Add localtime vs ntp server check just in case localtime is way off
# Add argparse and include target volume option, debug, etc.
# Add support for snapshotting multiple volumes
#
# v0.1 Initial script, catdevurandom


import boto # Note: AWS API credentials must be supplied in your user's homedir in a file called .boto for this to work.  See boto documentation: http://code.google.com/p/boto/w/list
import re
import datetime
import calendar
import syslog
import sys


def main():
    global debug
    debug = True
    syslog.openlog("aws_snapshot_manager.py", syslog.LOG_PID, syslog.LOG_LOCAL0)
    syslog.syslog('INFO: Starting snapshot management process')
    conn = start_aws_connection()
    selected_volume = select_volume(conn, "vol-140bd69d") # change this to the volume you'd like to use
    snapshot_result = take_snapshot(selected_volume)
    archival_snapshot_list = get_snapshot_list(conn)
    result = manage_snapshot_inventory(archival_snapshot_list)

def start_aws_connection():
    '''Initiate AWS API connection'''

    try:
        conn = boto.connect_ec2()
        if debug is True: syslog.syslog('DEBUG: Initiated %s successfully' % conn)
    except Exception:
        syslog.syslog('ERROR: Failed to connect to AWS')

    return conn

def select_volume(conn, volume_id):
    '''Select specified volume ID and return volume object'''

    volume_list = conn.get_all_volumes([volume_id])
    selected_volume = volume_list[0]

    if selected_volume is None:
        syslog.syslog('ERROR: Failed to locate %s' % volume_id)
    elif debug is True:
        syslog.syslog('DEBUG: Selected %s' % selected_volume)

    return selected_volume

def take_snapshot(selected_volume):
    '''Take snapshot of selected volume and add proper descriptor'''
    snapshot_description = 'Created by aws_snapshot_manager.py at ' + datetime.datetime.today().isoformat(' ')
    try:
        snapshot_result = selected_volume.create_snapshot(snapshot_description)
        syslog.syslog('INFO: Created %s successfully!' % snapshot_result)
    except:
        syslog.syslog('ERROR: Failed to create snapshot!  Cancelling job.')
        sys.exit(1)

    return snapshot_result

def get_snapshot_list(conn):
    '''Get a list of all snapshots with matching Description field'''
    description = 'Created by aws_snapshot_manager.py'
    all_snapshots = conn.get_all_snapshots()
    archival_snapshot_list = [i for i in all_snapshots if re.match(description, i.description)]
    if debug is True: syslog.syslog('DEBUG: %s snapshots currently in inventory' % len(archival_snapshot_list))
    if len(archival_snapshot_list) < 7: syslog.syslog('ERROR: Only %s snapshots currently in AWS inventory, we should always have at least 7!' % len(archival_snapshot_list))

    return archival_snapshot_list

def manage_snapshot_inventory(archival_snapshot_list):
    '''Check current date and process documented archival/deletion logic'''
    today = datetime.date.today()
    last_monthday = calendar.mdays[today.month]
    week_delta = today - datetime.timedelta(days=7)
    expired_snapshots = []

    for snapshot in archival_snapshot_list:
        snapshot_datetime = datetime.datetime.strptime(snapshot.start_time, '%Y-%m-%dT%H:%M:%S.%fZ')
        snapshot_date = snapshot_datetime.date()
        if snapshot.start_time <= week_delta.isoformat() and snapshot_date.day != calendar.mdays[snapshot_date.month]:
        # snapshots more than 7 days old are deleted, unless it was the last snapshot of any given month
            expired_snapshots.append(snapshot)

    if len(expired_snapshots) > 0:
        result = delete_snapshots(expired_snapshots)

    elif len(expired_snapshots) == 0:
        if debug is True:
            syslog.syslog('DEBUG: Not deleting any snapshots today')
        result = 0

    else:
        syslog.syslog('ERROR: How the hell did I come back with a negative number of snapshots?')
        result = 1

    return result

def delete_snapshots(expired_snapshots):
    for snapshot in expired_snapshots:
        syslog.syslog('INFO: Deleting %s (created on: %s)' % (snapshot, snapshot.start_time))
        try: 
            snapshot.delete()
        except:
            syslog.syslog('ERROR: Failed to delete %s' % snapshot)


if __name__ == '__main__':
    main()
