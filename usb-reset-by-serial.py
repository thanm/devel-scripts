#!/usr/bin/python3
"""Reset a USB device (presumbly android phone) by serial number.

Given a serial number, inspects connected USB devices and issues
USB reset to the one that matches.

"""

import fcntl
import getopt
import os
import re
import sys

import script_utils as u

# Serial number of device that we want to reset
flag_serial = None

USBDEVFS_RESET = ord("U") << (4*2) | 20


def issue_ioctl_to_device(device):
  """Issue USB reset ioctl to device."""

  try:
    fd = open(device, "wb")
  except IOError as e:
    u.error("unable to open device %s: "
            "%s" % (device, e.strerror))
  u.verbose(1, "issuing USBDEVFS_RESET ioctl() to %s" % device)
  fcntl.ioctl(fd, USBDEVFS_RESET, 0)
  fd.close()


def perform():
  """Main driver routine."""
  lines = u.docmdlines("usb-devices")
  dmatch = re.compile(r"^\s*T:\s*Bus\s*=\s*(\d+)\s+.*\s+Dev#=\s*(\d+).*$")
  smatch = re.compile(r"^\s*S:\s*SerialNumber=(.*)$")
  device = None
  found = False
  for line in lines:
    m = dmatch.match(line)
    if m:
      p1 = int(m.group(1))
      p2 = int(m.group(2))
      device = "/dev/bus/usb/%03d/%03d" % (p1, p2)
      u.verbose(1, "setting device: %s" % device)
      continue
    m = smatch.match(line)
    if m:
      ser = m.group(1)
      if ser == flag_serial:
        u.verbose(1, "matched serial, invoking reset")
        issue_ioctl_to_device(device)
        found = True
        break
  if not found:
    u.error("unable to locate device with serial number %s" % flag_serial)


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options] XXYYZZ

    where XXYYZZ is the serial number of a connected Android device.

    options:
    -d    increase debug msg verbosity level

    """ % os.path.basename(sys.argv[0]))
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_serial

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "d")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))
  if not args or len(args) != 1:
    usage("supply a single device serial number as argument")
  flag_serial = args[0]

  for opt, _ in optlist:
    if opt == "-d":
      u.increment_verbosity()


u.setdeflanglocale()
parse_args()
perform()
