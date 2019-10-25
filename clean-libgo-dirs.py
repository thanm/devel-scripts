#!/usr/bin/python3
"""Script to clean object files in GCC/Gollvm build dir libgo subdirs.

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


def do_gollvm_clean():
  """Clean a gollv build dir."""
  lgd = "tools/gollvm/libgo"
  u.verbose(1, "visiting %s" % lgd)
  do_clean(lgd)
  files = ["vet", "test2json", "buildid", "go", "gofmt", "cgo"]
  for f in files:
    p = "tools/gollvm/gotools/" + f
    if os.path.exists(p):
      u.verbose(1, "cleaning %s" % p)
      if not flag_dryrun:
        os.unlink(p)


def do_gccgo_clean():
  """Clean a gccgo build dir."""
  if not os.path.exists("config.log"):
    u.error("no 'config.log' here -- needs to be run in GCC build dir")
  lines = u.docmdlines("find . -depth -name libgo -print")
  lines.reverse()
  libgodirs = lines
  for lgd in libgodirs:
    if os.path.exists(lgd):
      u.verbose(1, "visiting %s" % lgd)
      do_clean(lgd)
  files = ["vet", "test2json", "buildid", "go", "gofmt", "cgo"]
  for f in files:
    p = "gotools/" + f
    if not flag_dryrun and os.path.exists(p):
      u.verbose(1, "cleaning %s" % p)
      os.unlink(p)


def perform():
  """Top level driver routine."""
  if os.path.exists("config.log"):
    do_gccgo_clean()
  elif os.path.exists("CMakeCache.txt"):
    do_gollvm_clean()
  else:
    u.error("no 'config.log' or 'CMakeCache.txt' here -- "
            "needs to be run in gccgo or gollvm build dir")


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options]

    options:
    -d    increase debug msg verbosity level
    -D    dryrun mode (echo commands but do not execute)

    """ % me)
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
