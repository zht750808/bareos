#!/usr/bin/env python
# -*- coding: utf-8 -*-
# BAREOS - Backup Archiving REcovery Open Sourced
#
# Copyright (C) 2014-2014 Bareos GmbH & Co. KG
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of version three of the GNU Affero General Public
# License as published by the Free Software Foundation, which is
# listed in the file LICENSE.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.
#
# Author: Maik Aussendorf
#
# Bareos python plugins class that adds files from a local list to
# the backup fileset

import bareosfd
from bareos_fd_consts import bJobMessageType, bFileType, bRCs
import os
import sys
import re
import psycopg2
import time
import datetime
from dateutil import parser
import dateutil
import BareosFdPluginLocalFileset

class BareosFdPluginPostgres(
    BareosFdPluginLocalFileset.BareosFdPluginLocalFileset
):  # noqa
    """
    Simple Bareos-FD-Plugin-Class that parses a file and backups all files
    listed there Filename is taken from plugin argument 'filename'
    """

    def __init__(self, context, plugindef):
        bareosfd.DebugMessage(
            context,
            100,
            "Constructor called in module %s with plugindef=%s\n"
            % (__name__, plugindef),
        )
        # Last argument of super constructor is a list of mandatory arguments
        super(BareosFdPluginPostgres, self).__init__(
            context, plugindef, ["postgresDataDir","walArchive"]
        )
        self.ignoreSubdirs = ["pg_wal", "pg_log"] 

        self.dbCon = None
        self.dbCursor = None
        # This will be set to True between SELCET pg_start_backup
        # and SELECT pg_stop_backup. We backup database file during
        # this time
        self.PostgressFullBackupRunning = False
        # Here we store items found in file backup_label, produced by Postgres
        self.labelItems = dict()
        # We will store the starttime from backup_label here
        self.backupStartTime = None
        self.backupLabelString = "Bareos.pgplugin.jobid.%d" %self.jobId
        self.rop_data = {}


    def check_options(self, context, mandatory_options=None):
        """
        Check for mandatory options and verify database connection
        """
        result = super(BareosFdPluginPostgres, self).check_options(
            context, mandatory_options)
        if not result == bRCs["bRC_OK"]:
            return result
        if not self.options['postgresDataDir'].endswith('/'):
            self.options['postgresDataDir'] += '/'
        if not self.options['walArchive'].endswith('/'):
            self.options['walArchive'] += '/'
        if 'ignoreSubdirs' in self.options:
            self.ignoreSubdirs = self.options['ignoreSubdirs']
        try:
            bareosfd.DebugMessage(
                context, 100, "Trying to connect to Postgres\n"
            )
            self.dbCon = psycopg2.connect("dbname=backuptest user=root")
            self.dbCursor = self.dbCon.cursor()
        except:
            bareosfd.JobMessage(
                context,
                bJobMessageType["M_ERROR"],
                "Could not connect to database\n",
            )
            return bRCs["bRC_Error"]
        return bRCs["bRC_OK"]

    def start_backup_job(self, context):
        """
        Make filelist in super class and tell Postgres
        that we start a backup now
        """
        bareosfd.DebugMessage(
            context,
            100,
            "start_backup_job in PostgresPlugin called",
        )

        # If level is not Full, we only backup newer WAL files
        if chr(self.level) == "F":
            startDir = self.options['postgresDataDir']
            bareosfd.DebugMessage(
                    context,
                    100,
                    "dataDir: %s\n" % self.options['postgresDataDir'],
            )
        else:
            startDir = self.options['walArchive']
            # TODO: optionally issue a SELECT pg_switch_wal(); here 

        # Gather files from Postgres data dir
        self.files_to_backup.append (startDir)
        for fileName in os.listdir(startDir):
            fullName = os.path.join (startDir, fileName)
            if os.path.isdir(fullName) and not fullName.endswith('/'):
                fullName += ('/')
                bareosfd.DebugMessage(
                    context,
                    100,
                    "fullName: %s\n" % fullName,
                )
            self.files_to_backup.append(fullName)
            if os.path.isdir(fullName) and fileName not in self.ignoreSubdirs:
                for topdir, dirNames, fileNames in os.walk(fullName):
                    for fileName in fileNames:
                        self.files_to_backup.append(os.path.join(topdir, fileName))
                    for dirName in dirNames:
                        fullDirName = os.path.join(topdir, dirName) + "/"
                        self.files_to_backup.append(fullDirName)

        # If level is not Full, we are done here
        if not chr(self.level) == "F":
            return bRCs["bRC_OK"]

        # For Full we check for a running job and tell Postgres that
        # we want to backup the DB files now.
        # Check for running Postgres Backup Job
        self.dbCursor.execute("SELECT pg_is_in_backup()")
        if self.dbCursor.fetchone()[0]:
            self.parseBackupLabelFile(context)
            bareosfd.JobMessage(
                    context,
                    bJobMessageType["M_FATAL"],
                    "Another Postgres Backup Operation \"%s\" is in progress. " % self.labelItems['LABEL'] +
                    "You may stop it using SELECT pg_stop_backup()" ,
                )
            return bRCs["bRC_Error"]

        bareosfd.DebugMessage(
                context, 100, "Send 'SELECT pg_start_backup' to Postgres\n"
            )
        #TODO: error handling
        self.dbCursor.execute("SELECT pg_start_backup('%s');" % self.backupLabelString)
        results = self.dbCursor.fetchall()
        bareosfd.DebugMessage(
                context, 150, "Start response: %s\n" % str(results)
            )
        labelFileName = self.options["postgresDataDir"] + "/backup_label"
        bareosfd.DebugMessage(
                context, 150, "Adding label file %s to fileset\n" % labelFileName
            )
        self.files_to_backup.append(labelFileName)
        bareosfd.DebugMessage(
            context,
            150,
            "Filelist: %s\n" % (self.files_to_backup),
        )

        self.PostgressFullBackupRunning = True
        return bRCs["bRC_OK"]


    def parseBackupLabelFile(self, context):
        labelFileName = self.options["postgresDataDir"] + "/backup_label"
        try:
            labelFile = open(labelFileName, "rb")
        except:
            bareosfd.JobMessage(
                context,
                bJobMessageType["M_WARNING"],
                "Could not open Label File %s" % (labelFileName),
            )
 
        for labelItem in labelFile.read().splitlines():
            print labelItem
            k,v = labelItem.split(':',1);
            self.labelItems.update({k.strip() : v.strip()})
        labelFile.close()
        bareosfd.DebugMessage(
                context, 150, "Labels read: %s\n" % str(self.labelItems)
            ) 
 

    def closeDbConnection(self, context):
        # TODO Error Handling
        # Get Backup Start Date
        self.parseBackupLabelFile(context)
        self.dbCursor.execute("SELECT pg_backup_start_time()")
        self.backupStartTime = self.dbCursor.fetchone()[0]
        # Tell Postgres we are done        
        self.dbCursor.execute("SELECT pg_stop_backup();")
        results = self.dbCursor.fetchall()
        bareosfd.JobMessage(
                   context,
                   bJobMessageType["M_INFO"],
                   "Database connection closed. " +
                   "CHECKPOINT LOCATION: %s, " % self.labelItems['CHECKPOINT LOCATION'] +
                   "START WAL LOCATION: %s\n" % self.labelItems['START WAL LOCATION'], 
        ) 
        self.PostgressFullBackupRunning = False


    def checkForWalFiles(self, context):
        '''
        Look for new WAL files and backup
        Backup start time is timezone aware, we need to add timezone
        to files' mtime to make them comparable
        '''
        # We have to add local timezone to the file's timestamp in order
        # to compare them with the backup starttime, which has a timezone
        tzOffset=-(time.altzone if (time.daylight and time.localtime().tm_isdst) else time.timezone)
        walArchive = self.options['walArchive']
        self.files_to_backup.append(walArchive)
        for fileName in os.listdir (walArchive):
            fullPath = os.path.join(walArchive, fileName)
            st = os.stat(fullPath)
            fileMtime = datetime.datetime.fromtimestamp(st.st_mtime)
            if fileMtime.replace(tzinfo=dateutil.tz.tzoffset(None, tzOffset)) > self.backupStartTime:
                bareosfd.DebugMessage(
                        context, 150, "Adding WAL file %s for backup\n" % fileName )
                self.files_to_backup.append(fullPath)

        if self.files_to_backup:
            return bRCs["bRC_More"]
        else:
            return bRCs["bRC_OK"]


    def end_backup_file(self, context):
        """
        Here we return 'bRC_More' as long as our list files_to_backup is not
        empty and bRC_OK when we are done
        """
        bareosfd.DebugMessage(
            context, 100, "end_backup_file() entry point in Python called\n"
        )
        if self.files_to_backup:
            return bRCs["bRC_More"]
        else:
            if self.PostgressFullBackupRunning:
                self.closeDbConnection (context)
                return self.checkForWalFiles(context)
            else:
                return bRCs["bRC_OK"]


    def end_backup_job(self, context):
        """
        Called if backup job ends, before ClientAfterJob 
        Make sure that dbconnection was closed in any way,
        especially when job was cancelled
        """
        if self.PostgressFullBackupRunning:
            self.closeDbConnection (context)
            self.PostgressFullBackupRunning = False
        return bRCs["bRC_OK"]


# vim: ts=4 tabstop=4 expandtab shiftwidth=4 softtabstop=4
