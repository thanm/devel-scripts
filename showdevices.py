#!/usr/bin/python3
"""Run 'adb devices' and show results in friendly way.

Runs 'adb devices' and integrates the results with environment
variables DEVTAGS and ANDROID_SERIAL to show model numbers for
connected devices.

"""

import getopt
import os
import re
import sys

import script_utils as u

valid_dispositions = {"device": 1,
                      "unauthorized": 1}

flag_showall = False


def read_devtags():
  """Read and post-process DEVTAGS environment var."""
  dt = os.getenv("DEVTAGS")
  chunks = dt.split(" ")
  sertotag = {}
  tagtoser = {}
  for chunk in chunks:
    (tag, ser) = chunk.split(":")
    if ser in sertotag:
      u.error("malformed DEVTAGS (more than one "
              "entry for serial number %s" % ser)
    if tag in tagtoser:
      u.warning("malformed DEVTAGS (more than one "
                "serial number for tag %s" % tag)
    sertotag[ser] = tag
    tagtoser[tag] = ser
  return (sertotag, tagtoser)


def perform():
  """Main driver routine."""
  andser = os.getenv("ANDROID_SERIAL")
  if andser:
    andser = andser.strip()
  else:
    andser = ""
  (serial_to_tag, tag_to_serial) = read_devtags()
  lines = u.docmdlines("adb devices")
  rxd1 = re.compile(r"^\* daemon not running.+$")
  rxd2 = re.compile(r"^\* daemon started.+$")
  rx1 = re.compile(r"^\s*(\S+)\s+(\S+)\s*$")
  devices_found = {}
  for line in lines[1:]:
    if rxd1.match(line) or rxd2.match(line):
      continue
    m = rx1.match(line)
    if not m:
      u.warning("unable to match adb output line: %s" % line)
      continue
    ser = m.group(1)
    disp = m.group(2)
    if disp not in valid_dispositions:
      u.warning("unknown device disposition %s in adb "
                "output line: %s" % (disp, line))
    sel = ""
    if ser == andser:
      sel = ">>"
    if ser not in serial_to_tag:
      tag = "???"
    else:
      tag = serial_to_tag[ser]
      devices_found[tag] = 1
    print("%2s %8s %16s %s" % (sel, tag, ser, disp))

  if flag_showall:
    for tag, ser in tag_to_serial.items():
      if tag in devices_found:
        continue
      print("%2s %8s %16s %s" % ("", tag, ser, "<unconnected>"))


def usage(msgarg=None):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options]

    options:
    -d    increase debug msg verbosity level
    -a    show disposition for all devices, not just those connected

    """ % os.path.basename(sys.argv[0]))
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_showall

  try:
    optlist, _ = getopt.getopt(sys.argv[1:], "da")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, _ in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-a":
      flag_showall = True


# ---------main portion of script -------------

u.setdeflanglocale()
parse_args()

# Check to make sure we can run adb
u.doscmd("which adb")

# run
perform()

# done
exit(0)
