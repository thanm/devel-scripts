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
flag_reverse = False


def docmd(cmd):
  """Execute a command."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmd(cmd)


def undolink(link):
  """Undo a symbolic link."""
  try:
    _ = os.readlink(link)
  except OSError as ose:
    u.warning("warning: %s not a link (%s), "
              "skipping" % (link, ose))
    return
  docmd("rm %s" % link)

  # Hack: sometimes gofrontend can get ahead of gcc trunk, in which case
  # we may try to check out something that does not exist. Check for this
  # case and work around it.
  # rev = "HEAD~1"
  rev = "HEAD"
  st = u.docmderrout("git show %s:%s" % (rev, link), "/dev/null", True)
  if st != 0:
    u.warning("skipping %s, does not exist in trunk yet" % link)
  else:
    docmd("git checkout %s" % link)


def perform():
  """Create links in a gcc trunk repo for gofrontend development."""
  msg = ""
  islink = True
  try:
    _ = os.readlink("gcc/go/gofrontend")
  except OSError as ose:
    msg = "%s" % ose
    islink = False
  if flag_reverse:
    if not islink:
      u.warning("warning: gcc/go/gofrontend not a link (%s), "
                "unable to proceed" % msg)
      return
    undolink("gcc/go/gofrontend")
    for item in os.listdir("libgo"):
      undolink("libgo/%s" % item)
    docmd("git checkout libgo")
  else:
    if islink:
      u.warning("warning: gcc/go/gofrontend is already a link, "
                "unable to proceed")
      return
    docmd("rm -rf gcc/go/gofrontend")
    docmd("ln -s ../../../gofrontend/go gcc/go/gofrontend")
    docmd("rm -rf libgo")
    docmd("mkdir libgo")
    libgo = "../gofrontend/libgo"
    for item in os.listdir(libgo):
      docmd("ln -s ../../gofrontend/libgo/%s libgo/%s" % (item, item))


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options]

    options:
    -d    increase debug msg verbosity level
    -R    reverse mode (undo links and restore files)
    -D    dryrun mode (echo commands but do not execute)

    """ % me
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_dryrun, flag_echo, flag_reverse

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "dDR")
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
    elif opt == "-R":
      flag_reverse = True

  if not os.path.exists("gcc"):
    usage("expected to find gcc subdir")
  if not os.path.exists("libgo"):
    usage("expected to find libgo subdir")
  if not os.path.exists("../gofrontend"):
    usage("expected to find ../gofrontend subdir")


parse_args()
u.setdeflanglocale()
perform()
