#!/usr/bin/python
"""Annotates -E preprocessed source input with line numbers.

Read std input, then annotate each line with line number based on previous
expanded line directives from -E output. Useful in the context of compiler
debugging.

"""

import getopt
import os
import re
import sys

import script_utils as u


flag_reverse = True


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options] < input > output

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
      flag_reverse = False


# Setup
u.setdeflanglocale()
parse_args()

# Read
lines = sys.stdin.readlines()
lnum = -1
matcher = re.compile(r"^\#\s+(\d+)\s+\"(\S+)\".*$")
for line in lines:
  m = matcher.match(line)
  if m:
    lnum = int(m.group(1))
    afile = m.group(2)
    print "<%s:%d>" % (afile, lnum)
    continue
  print "%d:%s" % (lnum, line.strip())
  lnum += 1
