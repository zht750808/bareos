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
from cryptography.fernet import Fernet
import BareosFdPluginLocalFileset
from BareosFdPluginBaseclass import *

class BareosFdPluginZeroKnowledge(
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
        super(BareosFdPluginZeroKnowledge, self).__init__(
            context, plugindef, ["filename"]
        )
        self.clearFileList = []
        self.decryptionMap = {}
        self.keyString = 'tFrjXtGYJz1thRpFHREPg8dOS5LEVk_3w6SJB3AjCKM='
        self.key=Fernet(self.keyString)


    def check_options(self, context, mandatory_options=None):
        """
        Check for mandatory options and verify database connection
        """
        result = super(BareosFdPluginZeroKnowledge, self).check_options(
            context, mandatory_options)
        return result
    

    def start_backup_job(self, context):
        result = super(BareosFdPluginZeroKnowledge, self).start_backup_job(
            context)
        if not result == bRCs["bRC_OK"]:
            return result
        self.clearFileList = self.files_to_backup
        self.files_to_backup = [] 
        for fileName in self.clearFileList:
            encrFileName = self.encryptFileName (fileName)
            self.decryptionMap[encrFileName] = fileName
            self.files_to_backup.append(encrFileName)
        bareosfd.DebugMessage(
            context,
            150,
            "Filelist: %s\n" % (self.files_to_backup),
        )
        return result


    def encryptFileName(self, fileName):
        return self.key.encrypt(fileName)


    def decryptFileName(self, fileName, context):
        bareosfd.DebugMessage(
            context,
            150,
            "decrypt fname: %s\n" % (fileName),
        )
        # strip prefix-Directory, if existent
        if '/' in fileName:
            dirPrefix, encrName = fileName.rsplit('/',1)
        else:
            dirPrefix = ''
            encrName = fileName
        return (dirPrefix + self.key.decrypt(encrName))


    def start_backup_file(self, context, savepkt):
        """
        Defines the file to backup and creates the savepkt. In this example
        only files (no directories) are allowed
        """
        bareosfd.DebugMessage(context, 100, "start_backup_file() called\n")
        if not self.files_to_backup:
            bareosfd.DebugMessage(context, 100, "No files to backup\n")
            return bRCs["bRC_Skip"]

        encryptedName = self.files_to_backup.pop()
        file_to_backup = encryptedName
        clearName = self.decryptionMap[encryptedName]

        bareosfd.DebugMessage(context, 100, "file: %s Clear: %s\n" %(file_to_backup, clearName))

        mystatp = bareosfd.StatPacket()
        statp = os.stat(clearName)
        # As of Bareos 19.2.7 attribute names in bareosfd.StatPacket differ from os.stat
        # In this case we have to translate names
        # For future releases consistent names are planned, allowing to assign the
        # complete stat object in one rush
        if hasattr (mystatp, 'st_uid'):
            mystatp = statp
        else:
            mystatp.mode = statp.st_mode
            mystatp.ino = statp.st_ino
            mystatp.dev = statp.st_dev
            mystatp.nlink = statp.st_nlink
            mystatp.uid = statp.st_uid
            mystatp.gid = statp.st_gid
            mystatp.size = statp.st_size
            mystatp.atime = statp.st_atime
            mystatp.mtime = statp.st_mtime
            mystatp.ctime = statp.st_ctime
        savepkt.fname = file_to_backup        
        # os.islink will detect links to directories only when
        # there is no trailing slash - we need to perform checks
        # on the stripped name but use it with trailing / for the backup itself
        if os.path.islink(clearName.rstrip('/')):
            savepkt.type = bFileType["FT_LNK"]
            savepkt.link = os.readlink(clearName.rstrip('/'))
            bareosfd.DebugMessage(context, 150, "file type is: FT_LNK\n")
        elif os.path.isfile(clearName):
            savepkt.type = bFileType["FT_REG"]
            bareosfd.DebugMessage(context, 150, "file type is: FT_REG\n")
        elif os.path.isdir(clearName):
            savepkt.type = bFileType["FT_DIREND"]
            savepkt.link = file_to_backup
            bareosfd.DebugMessage(context, 150, "file %s type is: FT_DIREND\n" % file_to_backup)
        else:
            bareosfd.JobMessage(
                context,
                bJobMessageType["M_WARNING"],
                "File %s of unknown type" % (file_to_backup),
            )
            return bRCs["bRC_Skip"]
            
        savepkt.statp = mystatp
        bareosfd.DebugMessage(context, 150, "file statpx " + str(savepkt.statp) + "\n")

        return bRCs["bRC_OK"]


    def plugin_io(self, context, IOP):
        '''
        Basic IO operations. Some tweaks here: IOP.fname is only set on file-open
        We need to capture it on open and keep it for the remaining procedures
        '''
        bareosfd.DebugMessage(
            context, 100, "plugin_io called with function %s filename %s\n" % (IOP.func, IOP.fname)
        )
        bareosfd.DebugMessage(context, 100, "self.FNAME is set to %s\n" % (self.FNAME))

        if IOP.func == bIOPS["IO_OPEN"]:
            self.FNAME = self.decryptFileName(IOP.fname, context)
            if os.path.isdir (self.FNAME):
                bareosfd.DebugMessage(context, 100, "%s is a directory\n" % (IOP.fname))
                self.fileType = "FT_DIR"
                bareosfd.DebugMessage(
                    context,
                    100,
                    "Did not open file %s of type %s\n" % (self.FNAME, self.fileType),
                )
                return bRCs["bRC_OK"]
            elif os.path.islink (self.FNAME):
                self.fileType = "FT_LNK"
                bareosfd.DebugMessage(
                    context,
                    100,
                    "Did not open file %s of type %s\n" % (self.FNAME, self.fileType),
                )
                return bRCs["bRC_OK"]
            else:
                self.fileType = "FT_REG"
                bareosfd.DebugMessage(
                    context,
                    150,
                    "file %s has type %s - trying to open it\n" % (self.FNAME, self.fileType),
                )
            try:
                if IOP.flags & (os.O_CREAT | os.O_WRONLY):
                    bareosfd.DebugMessage(
                        context,
                        100,
                        "Open file %s for writing with %s\n" % (self.FNAME, IOP),
                    )

                    dirname = os.path.dirname(self.FNAME)
                    if not os.path.exists(dirname):
                        bareosfd.DebugMessage(
                            context,
                            100,
                            "Directory %s does not exist, creating it now\n"
                            % (dirname),
                        )
                        os.makedirs(dirname)
                    self.file = open(self.FNAME, "wb")
                else:
                    bareosfd.DebugMessage(
                        context,
                        100,
                        "Open file %s for reading with %s\n" % (self.FNAME, IOP),
                    )
                    self.file = open(self.FNAME, "rb")
            except:
                IOP.status = -1
                return bRCs["bRC_Error"]
            return bRCs["bRC_OK"]

        elif IOP.func == bIOPS["IO_CLOSE"]:
            bareosfd.DebugMessage(context, 100, "Closing file " + "\n")
            if self.fileType == "FT_REG":
                self.file.close()
            return bRCs["bRC_OK"]

        elif IOP.func == bIOPS["IO_SEEK"]:
            return bRCs["bRC_OK"]

        elif IOP.func == bIOPS["IO_READ"]:
            if self.fileType == "FT_REG":
                bareosfd.DebugMessage(
                    context, 200, "Reading %d from file %s\n" % (IOP.count, self.FNAME)
                )
                IOP.buf = bytearray(IOP.count)
                IOP.status = self.file.readinto(IOP.buf)
                IOP.io_errno = 0
            else:
                bareosfd.DebugMessage(
                            context,
                            100,
                            "Did not read from file %s of type %s\n" % (self.FNAME, self.fileType),
                        )
                IOP.buf = bytearray()
                IOP.status = 0
                IOP.io_errno = 0
            return bRCs["bRC_OK"]

        elif IOP.func == bIOPS["IO_WRITE"]:
            bareosfd.DebugMessage(
                context, 200, "Writing buffer to file %s\n" % (self.FNAME)
            )
            self.file.write(IOP.buf)
            IOP.status = IOP.count
            IOP.io_errno = 0
            return bRCs["bRC_OK"]

    def create_file(self, context, restorepkt):
        """
        Creates the file to be restored and directory structure, if needed.
        Adapt this in your derived class, if you need modifications for
        virtual files or similar
        """
        bareosfd.DebugMessage(
            context,
            100,
            "create_file() entry point in Python called with %s\n" % (restorepkt),
        )
        FNAME = self.decryptFileName(restorepkt.ofname, context)
        dirname = os.path.dirname(FNAME.rstrip('/'))
        if not os.path.exists(dirname):
            bareosfd.DebugMessage(
                context, 200, "Directory %s does not exist, creating it now\n" % dirname
            )
            os.makedirs(dirname)
        # open creates the file, if not yet existing, we close it again right
        # aways it will be opened again in plugin_io.
        # But: only do this for regular files, prevent from
        # IOError: (21, 'Is a directory', '/tmp/bareos-restores/my/dir/')
        # if it's a directory
        if restorepkt.type == bFileType["FT_REG"]:
            open(FNAME, "wb").close()
        elif restorepkt.type == bFileType["FT_LNK"]:
            if not os.path.exists(FNAME.rstrip('/')):
                os.symlink(restorepkt.olname, FNAME.rstrip('/'))
        elif restorepkt.type == bFileType["FT_DIREND"]:
            if not os.path.exists(FNAME):
                os.makedirs(FNAME)
        restorepkt.create_status = bCFs["CF_EXTRACT"]
        return bRCs["bRC_OK"]


    def set_file_attributes(self, context, restorepkt):
        # Python attribute setting does not work properly with links
        if restorepkt.type == bFileType["FT_LNK"]:
            return bRCs["bRC_OK"]
        file_name = self.decryptFileName(restorepkt.ofname, context)
        file_attr = restorepkt.statp
        bareosfd.DebugMessage(context, 150, "Restore file " + file_name + " with stat " + str(file_attr) + "\n")
        os.chown (file_name, file_attr.uid, file_attr.gid)
        os.chmod (file_name, file_attr.mode)
        os.utime (file_name, (file_attr.atime, file_attr.mtime))
        return bRCs["bRC_OK"]





# vim: ts=4 tabstop=4 expandtab shiftwidth=4 softtabstop=4
