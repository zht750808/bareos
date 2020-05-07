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

from bareosfd import *
from bareos_fd_consts import bJobMessageType, bFileType, bRCs
import os
import sys
import re
import psycopg2
import time
import datetime
from dateutil import parser
import dateutil
import json
import BareosFdPluginLocalFileset
from BareosFdPluginBaseclass import *
from operator import itemgetter
import glob
from ConfigParser import SafeConfigParser

class BareosFdPluginSplitJobs(
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
        super(BareosFdPluginSplitJobs, self).__init__(
            context, plugindef
        )
        # preliminary List, before slicing a tuple of
        # filename, mtime, filesize
        self.preliminaryList = []
        # split for a part-job or regular for a regular incremental
        self.jobType = 'split'
        # TODO: make statusDir somewhat unique
        self.statusDir = (self.workingdir + '/status_splitJobs/')
        self.jobDescrFilePrefix = (self.statusDir + "splitJobDescription.")
        self.runningDir = self.statusDir + "/running/"
        self.myJobFile = ""
        self.metaInfo = {}
        self.splitJobMetaFile = self.statusDir + "splitJobMeta.txt"
        self.numParallelJobs = 1
        self.removeMetaFile = False 
        self.tzOffset = -(
            time.altzone
            if (time.daylight and time.localtime().tm_isdst)
            else time.timezone
        )

    def check_options(self, context, mandatory_options=None):
        """
        Check for mandatory options and verify database connection
        """
        result = super(BareosFdPluginSplitJobs, self).check_options(
            context, mandatory_options
        )
        if not result == bRCs["bRC_OK"]:
            return result
        # Accurate may cause problems with plugins
        accurate_enabled = GetValue(context, bVariable["bVarAccurate"])
        if accurate_enabled is not None and accurate_enabled != 0:
            JobMessage(
                context,
                bJobMessageType["M_FATAL"],
                "start_backup_job: Accurate backup not allowed please disable in Job\n",
            )
            return bRCs["bRC_Error"]
        if 'parallelJobs' in self.options:
            self.numParallelJobs = int(self.options['parallelJobs'])
        return bRCs["bRC_OK"]

    def append_file_to_backup(self, context, filename):
        """
        We add timestamp and size information for sorting and slicing
        """
        fileStat = os.stat(filename)        
        self.preliminaryList.append([filename,fileStat.st_mtime,fileStat.st_size])
        self.files_to_backup.append(filename)

    def sliceList (self, myList, i, maxChunks):
        """
        slice list into maxChunks parts and return the
        i. part as new list
        """
        k, m = divmod(len(myList), maxChunks)
        return (myList[i * k + min(i, m):(i + 1) * k + min(i + 1, m)])

    def readFileListFromFile(self, context):
        jobFiles = glob.glob(self.jobDescrFilePrefix+"[0-9]*")
        bareosfd.DebugMessage(
            context,
            100,
            "Found job files: %s with glob %s\n" % (jobFiles,self.jobDescrFilePrefix+".[0-9]*"),
        )
        myJobFile = ""
        if jobFiles and len(jobFiles) > 0:
            # TODO error handling / race condition handling
            self.myJobFile = jobFiles[0]
            os.rename(self.myJobFile, self.runningDir + os.path.basename(self.myJobFile))
            self.myJobFile = self.runningDir + os.path.basename(self.myJobFile)
            bareosfd.DebugMessage(
                context,
                100,
                "Trying to open file %s\n" % (self.myJobFile),
            )
            try:
                config_file = open(self.myJobFile, "rb")
            except:
                JobMessage(
                    context,
                    bJobMessageType["M_FATAL"],
                    "splitJob: Could not open file %s\n" %(self.myJobFile),
                )
                return False
            bareosfd.JobMessage(
                context,
                bJobMessageType["M_INFO"],
                "splitJob: Reading information from file %s\n" %self.myJobFile,
            )
            for listItem in config_file.read().splitlines():
                self.files_to_backup.append(listItem)
            config_file.close()
            # TODO: set SinceTime to lowValue (eventually set first line in jobFile)
        # no job file found, check for meta file
        else:
            if os.path.exists(self.splitJobMetaFile):
                # we have no job-file but a meta file
                # This means we are the first Incremental
                # running after the last split job
                # Read latest timestamp and use that as SinceTime
                # TODO: make sure no incr. is still running
                parser = SafeConfigParser()
                parser.read(self.splitJobMetaFile)
                maxTimestamp = parser.get('SplitJob','MaxTimestamp')
                bareosfd.JobMessage(
                    context,
                    bJobMessageType["M_INFO"],
                    "splitJob: first Incr. after split cycle. Using SinceTime from meta-file %s\n" %maxTimestamp ,
                )
                # TODO Set SinceTime to maxTimestamp
                # TODO Sanity check for orphaned jobs, redo unfinisched work
                # Remove meta-File after backup, if job finishes regularly
                self.removeMetaFile = True
                return False
            else:
                # No JobDescription nor Meta File found
                # We are just a regular Incremental job
                bareosfd.JobMessage(
                    context,
                    bJobMessageType["M_INFO"],
                    "splitJob: no description nor meta data found. Regular Job.\n",
                )
                # use full file list and let FD do the rest
                return False
        return True

    def start_backup_job(self, context):
        """
        Make filelist in super class and tell SplitJobs
        that we start a backup now
        """
        bareosfd.DebugMessage(
            context, 100, "start_backup_job in SplitJobsPlugin called",
        )
        if chr(self.level) == "F":
            result = super(BareosFdPluginSplitJobs, self).start_backup_job(context)
            self.preliminaryList = sorted(self.preliminaryList,key=itemgetter(1))
            bareosfd.DebugMessage(
                context, 150, "Preliminary list: %s" % (self.preliminaryList),
            )
            fileList = [i[0] for i in self.preliminaryList]
            # create working dir
            if not os.path.exists(self.runningDir):
                os.makedirs(self.runningDir)
            if self.numParallelJobs > len(fileList):
                self.numParallelJobs = len(fileList)
            # Create JobDescription file for each split-job
            for splitJobNum in range(self.numParallelJobs):
                fileSuffix = str(splitJobNum).zfill(len(str(self.numParallelJobs))+1)
                fileName = self.jobDescrFilePrefix + fileSuffix
                self.jobFile = open(fileName, "wb")
                splitList = self.sliceList(fileList,splitJobNum,self.numParallelJobs)
                self.jobFile.write("\n".join(splitList))
                self.jobFile.close()
            totalNumFiles = len(self.files_to_backup)
            self.files_to_backup=[]
            # Create meta data file
            metaFile = open (self.splitJobMetaFile, "wb")
            metaFile.write ("[SplitJob]\n")
            metaFile.write ("FullJobId=%s\n" %self.jobId)
            metaFile.write ("FullJobName=%s\n" %self.jobName)
            metaFile.write ("MaxTimestamp=%s\n" %self.preliminaryList[-1][1])
            metaFile.write ("FileTotals=%d\n" %totalNumFiles)
            metaFile.write ("Chunks=%d\n" %self.numParallelJobs)
            metaFile.close()
            bareosfd.JobMessage(
                    context,
                    bJobMessageType["M_INFO"],
                    "splitJob: writing %d job description files in %s. Total files to backup: %d\n"
                    % (self.numParallelJobs, self.statusDir , totalNumFiles)
            )
 
            return result
        elif chr(self.level) == "I":
            if self.readFileListFromFile (context):
                return bRCs["bRC_OK"]
            else:
                # use full list and SinceDate
                result = super(BareosFdPluginSplitJobs, self).start_backup_job(context)
                return result 
        else:
            JobMessage(
                context,
                bJobMessageType["M_FATAL"],
                "splitJob: Level %s not supported in splitJobs plugin\n" %(chr(self.level)),
            )
            return bRCs["bRC_Error"]
        return bRCs["bRC_OK"]

    def end_backup_job(self, context):
        """
        Called if backup job ends, before ClientAfterJob 
        Remove working file / jobDescription File
        TODO: make sure to remove file only, if job finishes regularly
        """
        if chr(self.level) == "I" and os.path.exists (self.myJobFile):
            try:
                os.remove(self.myJobFile)
            except Exception as e:
                bareosfd.JobMessage(
                    context,
                    bJobMessageType["M_ERROR"],
                    "splitJob: could not remove job file %s. \"%s\"" % (self.myJobFile, e.message),
                )
                return bRCs["bRC_Error"]
        if self.removeMetaFile and os.path.exists(self.splitJobMetaFile):
            try:
                os.remove(self.splitJobMetaFile)
            except Exception as e:
                bareosfd.JobMessage(
                    context,
                    bJobMessageType["M_ERROR"],
                    "splitJob: could not remove metadata file %s. \"%s\"" % (self.splitJobMetaFile, e.message),
                )
                return bRCs["bRC_Error"]
        return bRCs["bRC_OK"]


# vim: ts=4 tabstop=4 expandtab shiftwidth=4 softtabstop=4
