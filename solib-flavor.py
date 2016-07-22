#!/usr/bin/python
"""Script to check *.so for GCC or LLVM compilation.

Extracts .comment section and examines for proper vintage.

"""

from collections import defaultdict
import getopt
import os
import re
import sys

import script_utils as u


# Files to look at
flag_infiles = []

# Summarize version usage
flag_summarize = False

# key is version,
versioncount = defaultdict(int)


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options] <files>

    options:
    -d    increase debug msg verbosity level
    -s    summarize version usage
    """ % me
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_infiles, flag_summarize

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "ds")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, _ in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-s":
      flag_summarize = True
  if not args:
    usage("supply one or more filenames as arguments")
  flag_infiles = args


def visit(filename):
  """Examine specified file."""
  if not os.path.exists(filename):
    u.warning("unable to access file '%s', skipping" % filename)
    return
  u.verbose(1, "about to invoke readelf")
  lines = u.docmdlines("readelf -p .comment %s" % filename, True)
  if not lines:
    u.warning("unable to extract comment from %s, skipping" % filename)
    return
  matcher1 = re.compile(r"^\s*\[\s*\d+\]\s+(\S.+)$")
  matcher2 = re.compile(r"^GCC\:.+$")
  matcher3 = re.compile(r"^clang version \d.*$")
  res = ""
  sep = ""
  found = False
  comms = {}
  for line in lines:
    u.verbose(2, "line is %s" % line)
    m = matcher1.match(line)
    if not m:
      continue
    found = True
    comm = m.group(1).strip()
    u.verbose(1, "comm is %s" % comm)
    if comm in comms:
      continue
    comms[comm] = 1
    m2 = matcher2.match(comm)
    if m2:
      versioncount[comm] += 1
      res += sep + comm
      sep = ", "
    m3 = matcher3.match(comm)
    if m3:
      versioncount[comm] += 1
      res += sep + comm
      sep = ", "
  if not found:
    res = "<comment not found>"
    versioncount[res] += 1
  elif not res:
    res = "<unknown>"
    versioncount[res] += 1
  print "%s: %s" % (filename, res)


def summarize():
  """Summarize compiler usage."""
  rawtups = []
  for key, count in versioncount.iteritems():
    tup = (count, key)
    rawtups.append(tup)
  stups = sorted(rawtups, reverse=True)
  print ""
  print "File breakdown by compiler version:"
  for tup in stups:
    print "%d %s" % (tup[0], tup[1])
#
#......................................................................
#
# Main portion of script
#
parse_args()
u.setdeflanglocale()
for infile in flag_infiles:
  visit(infile)
if flag_summarize:
  summarize()
exit(0)
