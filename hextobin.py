#!/usr/bin/python
"""Converts hex numbers to binary.

Read stdin converting hex text to binary.

"""

import getopt
import os
import sys

import script_utils as u

flag_reverse = False


def convert(s):
  """Convert hex to binary or vice versa."""
  if flag_reverse:
    try:
      v = int(s, 10)
    except ValueError:
      return s
    return "0x" + hex(v)[2:].zfill(8)
  else:
    try:
      v = int(s, 16)
    except ValueError:
      return s
    return bin(v)[2:].zfill(8)



def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options]

    options:
    -d    increase debug msg verbosity level

    """ % os.path.basename(sys.argv[0])
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_reverse

  try:
    optlist, _ = getopt.getopt(sys.argv[1:], "dr")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, _ in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-r":
      flag_reverse = True


# Setup
u.setdeflanglocale()
parse_args()

# Read
lines = sys.stdin.readlines()
for line in lines:
  chunks = line.strip().split();
  res = []
  for chunk in chunks:
    res.append(convert(chunk))
  print " ".join(res)
