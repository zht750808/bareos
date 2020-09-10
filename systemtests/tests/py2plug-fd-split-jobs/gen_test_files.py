#!/usr/bin/python2
import string
import tempfile
import sys
import os
import random
import time

def randstring(l):
    return ''.join(random.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for x in range(l))

def mkdir(directory_name):
    """
    Utility Function for creating directories
    """
    try:
        os.stat(directory_name)
    except OSError:
        os.makedirs(directory_name)

l1 = 10
l2 = 10
l3 = 1
l4 = 1

print "Generating %d * %d * %d * %d = %d Testfiles ..." % (l1, l2, l3, l4, l1*l2*l3*l4)

for i in range(1, l1+1):
    di = "%d-%s" % (i, randstring(15))
    for j in range(1, l2+1):
        dj = "%d-%s" % (j, randstring(random.randint(20,30)))
        for k in range(1, l3+1):
          print "i=%d j=%d, k=%d" % (i, j, k)
          dk = "%d-%s" % (k, randstring(random.randint(30,40)))
          dir_name = "%s/%s/%s" % (di, dj, dk)
          mkdir(dir_name)
          for l in range(1,l4+1):
              file_name = randstring(random.randint(10,70))
              f = tempfile.NamedTemporaryFile(dir=dir_name, prefix=file_name, delete=False)
              f.write(time.strftime("%d %b %Y %H:%M:%S") + "\n")
              f.close()
