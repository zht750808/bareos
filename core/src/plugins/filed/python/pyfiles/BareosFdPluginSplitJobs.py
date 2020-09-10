#!/usr/bin/env python
# -*- coding: utf-8 -*-
# BAREOS - Backup Archiving REcovery Open Sourced
#
# Copyright (C) 2014-2020 Bareos GmbH & Co. KG
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
#from bareos_fd_consts import bJobMessageType, bFileType, bRCs
import os
import sys
import re
import time
import datetime
from dateutil import parser
import dateutil
import json
import BareosFdPluginLocalFileset
from BareosFdPluginBaseclass import *
from operator import itemgetter
import glob
from configparser import SafeConfigParser
#from ConfigParser import SafeConfigParser

class BareosFdPluginSplitJobs(
    BareosFdPluginLocalFileset.BareosFdPluginLocalFileset
):  # noqa
    """
    Simple Bareos-FD-Plugin-Class that parses a file and backups all files
    listed there Filename is taken from plugin argument 'filename'
    """

    def __init__(self,  plugindef):
        bareosfd.DebugMessage(
            
            100,
            "Constructor called in module %s with plugindef=%s\n"
            % (__name__, plugindef),
        )
        # Last argument of super constructor is a list of mandatory arguments
        super(BareosFdPluginSplitJobs, self).__init__(
             plugindef
        )
        # preliminary List, before slicing a tuple of
        # filename, mtime, filesize
        #self.sinceTime = bareosfd.GetValue( bVariable["bVarSinceTime"])
        self.sinceTime = bareosfd.GetValue(bVarSinceTime)
        self.accurate_enabled = bareosfd.GetValue(bVarAccurate)
        if self.accurate_enabled is not None and self.accurate_enabled != 0:
            self.accurate_enabled = True
            # Disable accurate for Full and split incrementals
        self.preliminaryList = []
        # split for a part-job or regular for a regular incremental
        self.jobType = 'split'
        self.statusDir = (self.workingdir + '/plugin_splitJobs_' + self.shortName + '/')
        self.jobDescrFilePrefix = (self.statusDir + "splitJobDescription.")
        self.runningDir = self.statusDir + "running/"
        self.pidDir = self.statusDir + "pid/"
        self.pidSection = "splitJobStatus"
        self.pidFileName = self.pidDir + "jobId." + str(self.jobId)
        self.pidHandle = None
        self.myJobFile = ""
        self.metaInfo = {}
        self.jobInfo = SafeConfigParser()
        self.jobInfo.add_section(self.pidSection)
        # os.getpid() always returns 999 ?!
        #self.jobInfo.set(self.pidSection, 'pid', str(os.getpid()))
        self.jobInfo.set(self.pidSection, 'jobId', str(self.jobId))
        self.jobInfo.set(self.pidSection, 'startTime', str(self.startTime))
        self.splitJobMetaFile = self.statusDir + "splitJobMeta.txt"
        self.numParallelJobs = 1
        self.totalFiles = 0
        self.currentFileCounter = 0
        self.removeMetaFile = False 
        self.mvFileCounter = 0
        # Max tries to move job File in possible race conditions
        self.maxFileMoveLimit = 30

    def check_options(self,  mandatory_options=None):
        """
        Check for mandatory options and verify database connection
        """
        result = super(BareosFdPluginSplitJobs, self).check_options(
             mandatory_options
        )
        if not result == bareosfd.bRC_OK:
            return result
        if 'parallelJobs' in self.options:
            self.numParallelJobs = int(self.options['parallelJobs'])
        return bareosfd.bRC_OK

    def writePidStatus(self):
        self.jobInfo.set(self.pidSection,"status", chr(bareosfd.GetValue( bVarJobStatus)))
        self.jobInfo.set(self.pidSection,"currentFileCounter", str(self.currentFileCounter))
        self.jobInfo.set(self.pidSection,"currentFileName", self.file_to_backup)
        self.pidHandle.truncate(0)
        self.jobInfo.write(self.pidHandle)

    def append_file_to_backup(self,  filename):
        """
        We add timestamp and size information for sorting and slicing
        """
        filenameEncoded = filename #.encode('unicode_escape')
        if os.path.islink (filename):
            fileStat = os.lstat(filename)
        else:
            fileStat = os.stat(filename)        
        self.preliminaryList.append([filenameEncoded,fileStat.st_mtime,fileStat.st_size])
        #self.preliminaryList.append([filename,fileStat.st_mtime,fileStat.st_size])
        self.files_to_backup.append(filenameEncoded)

    def sliceList (self, myList, i, maxChunks):
        """
        slice list into maxChunks parts and return the
        i. part as new list
        """
        k, m = divmod(len(myList), maxChunks)
        return (myList[i * k + min(i, m):(i + 1) * k + min(i + 1, m)])

    def getRunningSisterJobs (self):
        """
        Return list of pid Files, if found, empty list else
        """
        pidFiles = glob.glob(self.pidDir + "*")
        bareosfd.DebugMessage(
            
            100,
            "Found %d pid files in %s\n" % (len(pidFiles), self.pidDir),
        )
        return pidFiles

    def moveFile (self,  src, dst):
        try:
            os.rename (src, dst)
        except:
            return False
        return True

    def readFileListFromFile(self):
        jobFiles = glob.glob(self.jobDescrFilePrefix+"[0-9]*")
        bareosfd.DebugMessage(
            
            100,
            "Found job files: %s with glob %s\n" % (jobFiles,self.jobDescrFilePrefix+".[0-9]*"),
        )
        myJobFile = ""
        if jobFiles and len(jobFiles) > 0:
            self.myJobFile = jobFiles[0]
            dstName = (self.runningDir + os.path.basename(self.myJobFile))
            # try to move jobFile to running dir
            if not self.moveFile ( self.myJobFile, dstName):
                JobMessage(
                    
                    bareosfd.M_INFO,
                    "splitJob: Could not move job file %s to %s. Possible race condition\n" %(self.myJobFile, dstName),
                )
                time.sleep(3)
                if self.mvFileCounter < self.maxFileMoveLimit:
                    # try it again
                    self.mvFileCounter += 1
                    return self.readFileListFromFile()
                else:
                    JobMessage(
                        
                        bareosfd.M_FATAL,
                        "splitJob: Could not move job file %s to %s %d times. Giving up.\n" %(self.myJobFile, dstName, self.maxFileMoveLimit),
                    )
                    return False

            self.myJobFile = self.runningDir + os.path.basename(self.myJobFile)
            bareosfd.DebugMessage(
                
                100,
                "Trying to open file %s\n" % (self.myJobFile),
            )
            try:
                config_file = open(self.myJobFile, "r")
            except:
                JobMessage(
                    
                    bareosfd.M_FATAL,
                    "splitJob: Could not open file %s\n" %(self.myJobFile),
                )
                return False
            bareosfd.JobMessage(
                
                bareosfd.M_INFO,
                "splitJob: Reading information from file %s\n" %self.myJobFile,
            )
            for listItem in config_file.read().splitlines():
                self.files_to_backup.append(listItem.encode().decode('unicode_escape')) #self.files_to_backup.append(listItem.decode('string_escape'))

            config_file.close()
            # TODO: adapt this to sinceTime relevant for this job / optional since parameter
            bareosfd.DebugMessage(
                150,
                "Setting SinceTime to 1, backup all file from list",
            )
            bareosfd.SetValue(bVarSinceTime,1)
        # no job file found, check for running jobs / meta file
        else:
            if self.getRunningSisterJobs ():
                JobMessage(
                    
                    bareosfd.M_FATAL,
                    "splitJob: No job description but unfinished jobs found. Check %s\n" %(self.pidDir),
                )
                return False
            if os.path.exists(self.splitJobMetaFile):
                # we have no job-file but a meta file
                # This means we are the first Incremental
                # running after the last split job
                # Read latest timestamp and use that as SinceTime
                parser = SafeConfigParser()
                parser.read(self.splitJobMetaFile)
                maxTimestamp = parser.get('SplitJob','MaxTimestamp')
                bareosfd.JobMessage(
                    
                    bareosfd.M_INFO,
                    "splitJob: first Incr. after split cycle. Using SinceTime from meta-file %s\n" %maxTimestamp ,
                )
                bareosfd.SetValue(bVarSinceTime,int(float(maxTimestamp)))
                # Remove meta-File after backup, if job finishes regularly
                self.removeMetaFile = True
                return False
            else:
                bareosfd.JobMessage(
                    
                    bareosfd.M_INFO,
                    "splitJob: no description nor meta data found. Regular Job.\n",
                )
                # No JobDescription nor Meta File found
                # We are just a regular Incremental job
                # use full file list and let FD do the rest
                # Enable accurate if it was configured originally
                if self.accurate_enabled:
                    bareosfd.SetValue( bVarAccurate, 1)
                return False
        return True

    def start_backup_job(self):
        """
        Make filelist in super class and tell SplitJobs
        that we start a backup now
        """
        bareosfd.DebugMessage(
             100, "start_backup_job in SplitJobsPlugin called",
        )

        startTime = int(time.time())
        bareosfd.SetValue(bVarAccurate, 0)
        if chr(self.level) == "F":
            result = super(BareosFdPluginSplitJobs, self).start_backup_job()
            self.preliminaryList = sorted(self.preliminaryList,key=itemgetter(1))
            bareosfd.DebugMessage(
                 150, "Preliminary list: %s" % (self.preliminaryList),
            )
            fileList = [i[0] for i in self.preliminaryList]
            oneFile = fileList.pop(0)
            # create working dir
            if not os.path.exists(self.runningDir):
                os.makedirs(self.runningDir)
            if self.numParallelJobs > len(fileList):
                self.numParallelJobs = len(fileList)
            # Create JobDescription file for each split-job
            for splitJobNum in range(self.numParallelJobs):
                fileSuffix = str(splitJobNum).zfill(len(str(self.numParallelJobs))+1)
                fileName = self.jobDescrFilePrefix + fileSuffix
                self.jobFile = open(fileName, "w")
                splitList = self.sliceList(fileList,splitJobNum,self.numParallelJobs)
                self.jobFile.write("\n".join(splitList))
                self.jobFile.close()
            totalNumFiles = len(self.files_to_backup)
            # Full backup must not be completely empty, needs at least one file
            self.files_to_backup=[oneFile]
            # Create meta data file
            metaFile = open (self.splitJobMetaFile, "w")
            metaFile.write ("[SplitJob]\n")
            metaFile.write ("FullJobId=%s\n" %self.jobId)
            metaFile.write ("FullJobName=%s\n" %self.jobName)
            #metaFile.write ("MaxTimestamp=%s\n" %self.preliminaryList[-1][1])
            metaFile.write ("MaxTimestamp=%d\n" %startTime)
            metaFile.write ("FileTotals=%d\n" %totalNumFiles)
            metaFile.write ("Chunks=%d\n" %self.numParallelJobs)
            metaFile.close()
            bareosfd.JobMessage(
                    
                    bareosfd.M_INFO,
                    "splitJob: writing %d job description files in %s. Total files to backup: %d\n"
                    % (self.numParallelJobs, self.statusDir , totalNumFiles)
            )
 
            return result
        elif chr(self.level) == "I":
            if self.readFileListFromFile ():
                # Init process information and create pid file
                # os.getpid() always returns 999 in plugins - not usable here
                #self.pidFileName += str(os.getpid())
                if not os.path.exists(self.pidDir):
                    os.makedirs(self.pidDir)
                self.pidHandle = open(self.pidFileName, 'w')
                self.jobInfo.set(self.pidSection,"totalFiles", str(len(self.files_to_backup)))
                self.writePidStatus()
                return bareosfd.bRC_OK
            else:
                # use full list and SinceDate
                result = super(BareosFdPluginSplitJobs, self).start_backup_job()
                return result 
        else:
            JobMessage(
                
                bareosfd.M_FATAL,
                "splitJob: Level %s not supported in splitJobs plugin\n" %(chr(self.level)),
            )
            return bareosfd.bRC_Error
        return bareosfd.bRC_OK
 
    def start_backup_file(self,  savepkt):
        result = super(BareosFdPluginSplitJobs, self).start_backup_file(savepkt)
        #time.sleep(2)
        if result == bareosfd.bRC_OK:
            self.currentFileCounter += 1
        if self.pidHandle:
            self.writePidStatus ()
        return result

    def delete_file_if_exists(self,  fileName):
        if os.path.exists(fileName):
            try:
                os.remove(fileName)
            except Exception as e:
                bareosfd.JobMessage(
                    
                    bareosfd.M_ERROR,
                    "splitJob: could not remove file %s. \"%s\"" % (fileName, e.message),
                )
                return False
        return True

    def end_job(self):
        """
        Called if backup job ends, before ClientAfterJob 
        Remove working file / jobDescription File
        """
        bareosfd.DebugMessage(
             150, "end_job in SplitJobsPlugin called. Status: %s" %chr(bareosfd.GetValue(bVarJobStatus)),
        )
 
    def end_backup_job(self):
        """
        Called if backup job ends, before ClientAfterJob 
        Remove working file / jobDescription File
        """
        jobStatus = chr(bareosfd.GetValue(bVarJobStatus))
        bareosfd.DebugMessage(
             150, "end_backup_job in SplitJobsPlugin called. Status: %s" %jobStatus,
        )
        result = True
        if chr(self.level) == "I":
            if self.pidHandle:
                self.pidHandle.close()
            if jobStatus in ['A','f']:
                result = self.moveFile ( self.myJobFile, self.statusDir + os.path.basename(self.myJobFile))
            else:
                result += self.delete_file_if_exists ( self.myJobFile)
            result += self.delete_file_if_exists( self.pidFileName)
        if self.removeMetaFile:
            result += self.delete_file_if_exists(self.splitJobMetaFile)
        if result:
            return bareosfd.bRC_OK
        else:
            return bareosfd.bRC_Error



# vim: ts=4 tabstop=4 expandtab shiftwidth=4 softtabstop=4
