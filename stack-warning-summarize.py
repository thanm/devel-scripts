#!/usr/bin/python
"""Summarize stack frame warnings.

Read stack frame size warnings, then summarizes the results. Reads from stdin.

"""

import getopt
import os
import re
import sys

import script_utils as u

flag_breakdown = False

def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options] < input > output

    options:
    -d    increase debug msg verbosity level
    -b    emit breakdown of functions and stack sizes

    """ % os.path.basename(sys.argv[0])
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_breakdown

  try:
    optlist, _ = getopt.getopt(sys.argv[1:], "db")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, _ in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-b":
      flag_breakdown = True


# Setup
u.setdeflanglocale()
parse_args()

# Maps function name to stack frame size
funcdict = {}

# Read
lines = sys.stdin.readlines()
matcher = re.compile(r"^.+warning: stack frame size of (\d+) bytes "
                     r"in function '\s*(\S.+)\s*'\s"
                     r"\[\-Wframe\-larger\-than\=\]")
for line in lines:
  m = matcher.match(line)
  if m:
    sbytes = int(m.group(1))
    fcn = m.group(2)
    if fcn in funcdict:
      sbytes = max(funcdict[fcn], sbytes)
    funcdict[fcn] = sbytes

if flag_breakdown:
  sfun = sorted(funcdict.keys())
  for sf in sfun:
    print "%5d %s" % (funcdict[sf], sf)

# Summarize
stacksum = sum(funcdict[i] for i in funcdict.keys())
print "Functions: %d" % len(funcdict.keys())
print "Accum size: %d" % stacksum
