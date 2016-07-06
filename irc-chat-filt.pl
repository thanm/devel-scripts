#!/usr/bin/python
"""Filter out input lines from irc chat log

Read std input, filter out any line wthat matches a series of
'uninteresting' patterns from IRC chat log.

"""

import getopt
import os
import re
import sys

import script_utils as u

flag_infile = None
flag_outfile = None


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options] < input > output

    options:
    -d    increase debug trace level
    -i F  read from input file F
    -o G  write output to file G


    """ % os.path.basename(sys.argv[0])
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_infile, flag_outfile

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "di:o:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  if args:
    usage("extra unknown arguments")
  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-i":
      flag_infile = arg
    elif opt == "-o":
      flag_outfile = arg


def perform_filt(inf, outf):
  """Perform filtering."""
  pats = [ r"^\*\s+\S+\s+has\s+quit.*$",
           r"^.+has joined \#llvm\s*$",
           r"^\s*\*\s+\S+\s+is now known as .+$",
           r"^\s*<\S+bot\>\s+r\d+\s+\(\S+\).*",
           r"^\s*\*\s+\S+\s+gives channel operator status.*$",
           r"^\s*\S+\s+build\s+\S+\s+of\s+\S+\s+is\s+complete.*$" ]

  matchers = []
  for p in pats:
    m = re.compile(p)
    matchers.append(m)

  while True:
    line = inf.readline()
    if not line:
      break
    found = False
    for m in matchers:
      r = m.match(line)
      if r:
        found = True
        break
    if not found:
      outf.write(line)


def perform():
  """Main driver routine."""
  inf = sys.stdin
  outf = sys.stdout
  if flag_infile:
    try:
      inf = open(flag_infile, "rb")
    except IOError as e:
      u.error("unable to open input file %s: "
              "%s" % (flag_infile, e.strerror))
  if flag_outfile:
    try:
      outf = open(flag_outfile, "wb")
    except IOError as e:
      u.error("unable to open output file %s: "
              "%s" % (flag_outfile, e.strerror))
  perform_filt(inf, outf)


# Main
u.setdeflanglocale()
parse_args()
perform()
