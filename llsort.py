#!/usr/bin/python
"""Sorts input lines by order of decreasing line length.

Read std input, then emit output lines in decreasing/increasing order
of line length.

"""

from collections import defaultdict
import getopt
import os
import sys

import script_utils as u


flag_reverse = True


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options]

    options:
    -d    increase debug msg verbosity level
    -r    reverse send of sort (increasing length)

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
d = defaultdict(list)
lines = sys.stdin.readlines()
for line in lines:
  ll = len(line)
  d[ll].append(line)

# Sort
dkeys = d.keys()
dkeys.sort(reverse=flag_reverse)

# Output
for idx in dkeys:
  llist = d[idx]
  for ln in llist:
    sys.stdout.write(ln)
