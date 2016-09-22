#!/usr/bin/python
"""Set up GCC repository for gccgo development.

Developing gccgo requires a copy of the gofrontend repository
along side a GCC repository, with soft links from gcc into
gofrontend. This script automates the process of creating
the necessary links. The assumption is that the root repo
contains "gcc-trunk" (GCC repo) and "gofrontend" at the
same level.

"""

import getopt
import os
import sys

import script_utils as u

flag_dryrun = False
flag_echo = False


def dochdir(thedir):
  """Switch to dir."""
  if flag_echo:
    sys.stderr.write("cd " + thedir + "\n")
  if flag_dryrun:
    return
  try:
    os.chdir(thedir)
  except OSError as err:
    u.error("chdir failed: %s" % err)


def docmd(cmd):
  """Execute a command."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmd(cmd)


def perform():
  """Create links in a gcc trunk repo for gofrontend development."""
  docmd("rm -rf gcc/go/gofrontend")
  docmd("ln -s ../../../gofrontend/go gcc/go/gofrontend")
  docmd("rm -rf libgo")
  docmd("mkdir libgo")
  libgo = "../gofrontend/libgo"
  for item in os.listdir(libgo):
    docmd("ln -s ../../gofrontend/libgo/%s libgo/%s" % (item, item))
  dochdir("..")


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options]

    options:
    -d    increase debug msg verbosity level
    -D    dryrun mode (echo commands but do not execute)

    """ % me
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_dryrun, flag_echo

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "dD")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))
  if args:
    usage("unknown extra args")

  for opt, _ in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-D":
      flag_dryrun = True
      flag_echo = True

  if not os.path.exists("gcc"):
    usage("expected to find gcc subdir")
  if not os.path.exists("libgo"):
    usage("expected to find libgo subdir")
  if not os.path.exists("../gofrontend"):
    usage("expected to find ../gofrontend subdir")


parse_args()
u.setdeflanglocale()
perform()
