#!/usr/bin/python
"""Pull any tombstone files from the connected Android device.

Uses 'adb' to inspect and pull any tombstone files from the connected
device, installing them in /tmp/tombstones/<dev>.

"""

import getopt
import os
import re
import sys

import script_utils as u


# Device tag
whichdev = None


def collectem():
  """Locate and upload tombstones."""

  # Need root access to get at /data/tombstones
  u.doscmd("adb root")

  # See what's available
  lines = u.docmdlines("adb shell ls -l /data/tombstones")

  # Things we found
  fnames = []

  # -rw------- system   system      56656 2015-05-25 03:01 tombstone_09
  matcher = re.compile(r"^\S+\s+\S+\s+\S+\s+\d+\s+(\S+)\s+(\S+)\s+(tomb\S+)\s*$")
  for line in lines:
    u.verbose(3, "line is: %s" % line)
    m = matcher.match(line)
    if m:
      datestr = m.group(1)
      timestr = m.group(2)
      fname = m.group(3)
      fnames.append(fname)
      u.verbose(1, ("found tombstone %s date %s time %s" %
                    (fname, datestr, timestr)))
      u.docmd("mkdir -p /tmp/tombstones/%s" % whichdev)
      newname = ("/tmp/tombstones/%s/%s_%s_%s" %
                 (whichdev, fname, datestr, timestr))
      u.docmd("adb pull /data/tombstones/%s %s_tmp" % (fname, newname))
      if os.path.exists(newname):
        # already there?
        rc = u.docmdnf("cmp -s %s %s_tmp" % (newname, newname))
        if rc == 0:
          print "file %s already uploaded, skipping..." % fname
        else:
          print "overwriting existing %s with new version" % fname
      else:
        u.docmdnf("mv %s_tmp %s" % (newname, newname))
        print "uploaded new tombstone to %s" % newname

  # Anything there?
  if not fnames:
    print "No tombstones found... terminating."


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

  global whichdev

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "d")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, _ in optlist:
    if opt == "-d":
      u.increment_verbosity()

  if args:
    usage("unrecognized arg")

  # Check to make sure we can run adb
  u.doscmd("which adb")

  # Collect device flavor
  lines = u.docmdlines("whichdevice.sh")
  if len(lines) != 1:
    u.error("unexpected output from whichdevice.sh")
  whichdev = lines[0].strip()
  u.verbose(1, "device: %s" % whichdev)


# ---------main portion of script -------------

parse_args()
u.setdeflanglocale()

# Check to make sure we can run adb
u.doscmd("which adb")

# Main helper routine
collectem()
