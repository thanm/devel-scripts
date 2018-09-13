#!/usr/bin/python
"""Dump out .go_exports for a gccg-compiled object or library."""

import getopt
import os
import re
import sys

import script_utils as u

flag_infiles = []


def examine(afile):
  """Dump go exports for specified file."""

  # Handle archives
  objfile = afile
  lines = u.docmdlines("ar t %s" % afile, True)
  if lines:
    # Extract elem from archive
    if not lines:
      u.warning("skipping %s, doesn't appear to be an archive" % afile)
      return
    elem = lines[0].strip()
    u.verbose(1, "%s contains %s" % (afile, elem))
    rc = u.docmdnf("ar x %s %s" % (afile, elem))
    if rc:
      u.warning("skipping %s, can't extract object" % afile)
      return
    objfile = elem

  # Handle objects
  cmd = ("objcopy -O binary --only-section=.go_export "
         "--set-section-flags .go_export=alloc %s "
         "go_export.txt" % objfile)
  rc = u.docmdnf(cmd)
  if rc:
    u.warning("skipping %s, can't extract export "
              "data (cmd failed: %s)" % (objfile, cmd))
    return
  try:
    inf = open("go_export.txt", "rb")
  except IOError as e:
    u.error("unable to open go_export.txt: "
            "%s" % e.strerror)
  print "== %s ==" % afile
  lines = inf.readlines()
  for line in lines:
    print line.strip()
  inf.close()
  if objfile != afile:
    os.unlink(objfile)


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options] file1 file2 ... fileN

    options:
    -d    increase debug msg verbosity level

    """ % os.path.basename(sys.argv[0])
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  try:
    optlist, args = getopt.getopt(sys.argv[1:], "d")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))
  if not args:
    usage("supply one or more object files or archives as arguments")

  for opt, _ in optlist:
    if opt == "-d":
      u.increment_verbosity()
  for a in args:
    if not os.path.exists(a):
      u.warning("failed to open/access '%s' -- skipping" % a)
    else:
      flag_infiles.append(a)


# Setup
u.setdeflanglocale()
parse_args()
here = os.getcwd()
for fil in flag_infiles:
  examine(fil)
