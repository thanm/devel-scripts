#!/usr/bin/python3
"""Script to create LNT trunk development volume.

Creates BTRFS subvolume with trunk LNT and LLVM test suite
clients, plus virtual env for running lnt/lit.

"""

import getopt
import os
import sys

import script_utils as u


# Name of dest subvolume
flag_subvol = None

# Echo command before executing
flag_echo = True

# Dry run mode
flag_dryrun = False

# Name of LLVM build dir from which to draw compilers
flag_llvm_build = None


# Various repositories
lnt_git = "http://llvm.org/git/lnt.git"
testsuite_git = "http://llvm.org/git/test-suite.git"


def docmd(cmd):
  """Execute a command."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmd(cmd)


def doscmd(cmd):
  """Execute a command."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.doscmd(cmd)


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


def emit_script_to_file(wf):
  """Emit test script to file handle."""
  script = """#!/bin/bash
ARG=$1
COMP_UNDER_TEST=%s/bin/clang
if [ \"x$ARG\" != \"x\" ]; then
  COMP_UNDER_TEST=$ARG/bin/clang
  if [ ! -x $COMP_UNDER_TEST ]; then
    echo error: $COMP_UNDER_TEST not executable
    exit 1
  fi
fi

source ./virtualenv/bin/activate

exec lnt runtest nt -j40 \\
   --sandbox ./results \\
   --cc $COMP_UNDER_TEST \\
   --test-suite ./test-suite
""" % flag_llvm_build
  wf.write(script)


def emit_scripts():
  """Emit script to kick off testing."""
  if flag_dryrun:
    sys.stderr.write("emitting script:\n")
    emit_script_to_file(sys.stderr)
  else:
    cmdfile = "./dorun.sh"
    with open(cmdfile, "w") as wf:
      emit_script_to_file(wf)
      wf.close()
    u.verbose(1, "script emitted to dorun.sh")


def do_subvol_create():
  """Create new LNT/testsuite trunk subvolume."""
  here = os.getcwd()
  ssdroot = u.determine_btrfs_ssdroot(here)
  docmd("snapshotutil.py mkvol %s" % flag_subvol)
  dochdir(ssdroot)
  dochdir(flag_subvol)
  u.verbose(1, "cloning LNT")
  doscmd("git clone %s" % lnt_git)
  u.verbose(1, "cloning test suite")
  doscmd("git clone %s" % testsuite_git)
  doscmd("virtualenv virtualenv")
  doscmd("./virtualenv/bin/python ./lnt/setup.py develop")


def perform():
  """Main driver routine."""
  do_subvol_create()
  emit_scripts()


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options]

    options:
    -d    increase debug msg verbosity level
    -s S  subvolume name to create is S
    -b B  draw compilers to test from LLVM build dir B
    -e    echo commands before executing
    -D    dryrun mode (echo commands but do not execute)

    Example 1: creates new subvolume 'lnt-blah'

      %s -s lnt-blah -b /ssd/llvm-work/build.opt

    """ % (me, me))
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_subvol, flag_echo, flag_dryrun, flag_llvm_build
  global flag_echo

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "deDs:b:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))
  if args:
    usage("unknown extra arguments")

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-D":
      flag_dryrun = True
      flag_echo = True
    elif opt == "-e":
      flag_echo = True
    elif opt == "-s":
      flag_subvol = arg
    elif opt == "-b":
      flag_llvm_build = arg

  if not flag_subvol:
    usage("specify subvol name with -s")
  if not flag_llvm_build:
    usage("specify default LLVM compiler build dir with -b")
  clang = "%s/%s" % (flag_llvm_build, "bin/clang")
  if not os.path.exists(clang):
    usage("unable to locate clang in %s/bin" % flag_llvm_build)


#
#......................................................................
#
# Main portion of script
#
parse_args()
u.setdeflanglocale()
perform()
