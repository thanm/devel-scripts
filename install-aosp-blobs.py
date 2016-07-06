#!/usr/bin/python
"""Install blobs for a specific device.

Install blobs into an Android client for a specific device: N5/N7/N9.

"""

import getopt
import os
import re
import sys

import script_utils as u


# Which device? E.g. N5/N7, etc
flag_device = None

# Where to put blobs once we've downloaded them
flag_archive_dir = None


def install_blob(blob, devdir):
  """Install a single blob."""

  # Determine blob name
  blobpath = "%s/%s" % (devdir, blob)
  lines = u.docmdlines("tar tzf %s" % blobpath)
  if len(lines) != 1:
    u.error("error while examining blob %s: expected single file" % blob)

  # Unpack
  blobfile = lines[0]
  u.verbose(1, "unpacking blob %s" % blob)
  u.docmd("tar xzf %s" % blobpath)

  # Invoke installer
  u.docmd("blobinstall.py %s" % blobfile)


def perform_install():
  """Install all blobs for a specific device."""

  # Check for device subdir in archive dir
  devdir = "%s/cur/%s" % (flag_archive_dir, flag_device)
  if not os.path.exists(devdir):
    u.warning("error: unable to locate %s subdir in "
              "%s/cur" % (flag_device, flag_archive_dir))
    u.warning("consider running download-aosp-blobs.py")
    exit(1)

  # Pick up all blobs in dir
  for afile in os.listdir(devdir):
    install_blob(afile, devdir)


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options] <device>

    options:
    -d     increase debug msg verbosity level
    -a D   pull blobs from archive dir D (default
           is to look in ~/blobs)

    Installs AOSP blobs for specified device (options: N5, N, N6, N9).
    Must be run from root of android client (after running 'lunch').

    """ % os.path.basename(sys.argv[0])
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_device, flag_archive_dir

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "da:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-a":
      flag_archive_dir = arg

  # Use $HOME/aosp_blobs if -a not specified
  if not flag_archive_dir:
    homedir = os.getenv("HOME")
    if not homedir:
      u.error("no setting for $HOME environment variable -- cannot continue")
    flag_archive_dir = "%s/blobs" % homedir
    sys.stderr.write("... archive dir not specified, "
                     "using %s\n" % flag_archive_dir)

  # Error checking
  if not os.path.exists(flag_archive_dir):
    u.error("archive dir %s doesn't exist" % flag_archive_dir)
  if not os.path.isdir(flag_archive_dir):
    u.error("archive dir %s not a directory" % flag_archive_dir)

  if len(args) != 1:
    u.error("provide at most one device (N5, N7, etc) as cmd line arg")
  flag_device = args[0]

  dmatch = re.compile(r"^N\d$$")
  m = dmatch.match(flag_device)
  if m is None:
    u.error("device argument not in form 'N{0-9}'")

  abt = os.getenv("ANDROID_BUILD_TOP")
  if abt is None:
    u.error("ANDROID_BUILD_TOP not set (did you run lunch?)")
  apo = os.getenv("ANDROID_PRODUCT_OUT")
  if apo is None:
    u.error("ANDROID_PRODUCT_OUT not set (did you run lunch?)")

  # Switch to abt
  print "cd %s" % abt
  os.chdir(abt)


#----------------------------------------------------------------------
# Main portion of script
#
parse_args()
perform_install()
