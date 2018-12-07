#!/usr/bin/python
"""Dump out .go_exports for a gccg-compiled object or library."""

import getopt
import os
import re
import sys
import tempfile

import script_utils as u

flag_infiles = []


def examine(afile):
  """Dump go exports for specified file."""

  objfile = afile
  arcmd = "ar t %s" % afile

  # Run 'ar' command, suppressing error output. If
  # if succeeds, then continue on the ar path, otherwise
  # treat input as an object.
  if u.doscmd(arcmd, True, True):
    # Handle archives
    lines = u.docmdlines(arcmd, True)
    if not lines:
      u.warning("skipping %s, can't index archive %s", afile)
      return
    # Extract elem from archive
    elem = lines[0].strip()
    u.verbose(1, "%s contains %s" % (afile, elem))
    rc = u.docmdnf("ar x %s %s" % (afile, elem))
    if rc:
      u.warning("skipping %s, can't extract object" % afile)
      return
    objfile = elem

  gexptemp = tempfile.NamedTemporaryFile(mode="w",
                                         prefix="go_export",
                                         delete=True)

  # Handle objects
  cmd = ("objcopy -O binary --only-section=.go_export "
         "--set-section-flags .go_export=alloc %s "
         "%s" % (objfile, gexptemp.name))
  rc = u.docmdnf(cmd)
  if rc:
    u.warning("skipping %s, can't extract export "
              "data (cmd failed: %s)" % (objfile, cmd))
    return
  try:
    inf = open(gexptemp.name, "rb")
  except IOError as e:
    u.error("unable to open tempfile %s: "
            "%s" % (gexptemp.name, e.strerror))
  print "== %s ==" % afile
  lines = inf.readlines()
  if not lines:
    u.warning("skipping %s, no .go_export section present" % objfile)
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
