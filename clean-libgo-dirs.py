#!/usr/bin/python
"""Script to clean all object files in libgo subdirs in GCC build dir.

"""

import getopt
import os
import sys

import script_utils as u

# Dry run mode
flag_dryrun = False

# Echo commands mode
flag_echo = False


def docmd(cmd):
  """Execute a command."""
  if flag_echo or flag_dryrun:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmd(cmd)


def dochdir(thedir):
  """Switch to dir."""
  if flag_echo or flag_dryrun:
    sys.stderr.write("cd " + thedir + "\n")
  try:
    os.chdir(thedir)
  except OSError as err:
    u.error("chdir failed: %s" % err)


def do_clean(subdir):
  """Clean this libgo dir."""
  flavs = (".o", "gox", ".a", ".so", ".lo", ".la")
  here = os.getcwd()
  dochdir(subdir)
  if flag_dryrun:
    u.verbose(0, "... cleaning %s" % subdir)
  else:
    cmd = "find . -depth "
    first = True
    for item in flavs:
      if not first:
        cmd += " -o "
      first = False
      cmd += "-name '*%s' -print" % item
    lines = u.docmdlines(cmd)
    lines.reverse()
    debris = lines
    for d in debris:
      if not d:
        continue
      u.verbose(1, "toclean '%s'" % d)
      os.unlink(d)
  dochdir(here)


def perform():
  """Top level driver routine."""
  if not os.path.exists("config.log"):
    u.error("no 'config.log' here -- needs to be run in GCC build dir")
  lines = u.docmdlines("find . -depth -name libgo -print")
  lines.reverse()
  libgodirs = lines
  for lgd in libgodirs:
    u.verbose(1, "visiting %s" % lgd)
    do_clean(lgd)


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
    optlist, args = getopt.getopt(sys.argv[1:], "deD")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))
  if args:
    usage("unknown extra args")

  for opt, _ in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-e":
      flag_echo = True
    elif opt == "-D":
      flag_dryrun = True


parse_args()
u.setdeflanglocale()
perform()
