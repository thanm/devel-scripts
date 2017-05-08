#!/usr/bin/python
"""Test a specified gccgo/gofrontend patch.

This script automates some of the steps needed to test a patch
to gofrontend, including:
- doing a git pull within gofrontend
- creating a patch branch
- pulling the patch onto the branch
- updating git in gcc trunk
- kicking off build and test

"""

import getopt
import os
import sys

import script_utils as u

flag_dryrun = False
flag_echo = False
flag_change = None
flag_branchname = None
flag_build_dir = "build-gcc-dbg"
flag_patch = 1
flag_gitrepo = "https://go.googlesource.com/gofrontend"


def docmd(cmd):
  """Execute a command."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmd(cmd)


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


def formrefname():
  """Form name of refs to pull."""
  cstr = "%d" % flag_change
  lasttwo = "%c%c" % (cstr[-2], cstr[-1])
  return "refs/changes/%s/%s/%d" % (lasttwo, flag_change, flag_patch)


def update_gofrontend():
  """Make the necessary git updates/changes to gofrontend."""
  dochdir("gofrontend")
  docmd("git checkout master")
  docmd("git pull")
  docmd("git checkout -b %s" % flag_branchname)
  docmd("git fetch %s %s" % (flag_gitrepo, formrefname()))
  docmd("git cherry-pick FETCH_HEAD")
  dochdir("..")


def update_gcctrunk():
  """Make the necessary git updates/changes to GCC trunk."""
  dochdir("gcc-trunk")
  docmd("setup-gccgo-trunk-links.py -R")
  docmd("git checkout master")
  docmd("git pull")
  docmd("setup-gccgo-trunk-links.py")
  dochdir("..")


def dobuild():
  """Run the build and test."""
  dochdir(flag_build_dir)
  try:
    with open("tmp.sh", "w") as wf:
      wf.write("#/bin/sh\n")
      scriptbody = """\
echo "make -j20 all 1> berr.txt 2>&1"
make -j20 all 1> berr.txt 2>&1
if [ $? != 0 ]; then
echo "** build failed, skipping tests"
emacs berr.txt &
exit 9
fi
echo "make -j20 check-go 1> terr.txt 2>&1"
make -j20 check-go 1> terr.txt 2>&1
if [ $? != 0 ]; then
echo "** test failed"
emacs berr.txt terr.txt &
exit 9
fi
echo "result: PASS"
emacs berr.txt terr.txt &"""
      wf.write(scriptbody)
  except IOError:
    u.error("open failed for tmp.sh")
  docmd("sh tmp.sh")


def perform():
  """Main driver."""
  update_gofrontend()
  update_gcctrunk()
  dobuild()


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage: %s -c X -b Y [options]

    options:
    -c X  gerrit change number is X
    -b Y  use temporary branch name Y
    -p N  patch set number is N (default: 1)
    -B D  perform build in build dir D (def: build-gcc-dbg)

    -d    increase debug msg verbosity level
    -e    echo commands as they are being executed
    -D    dryrun mode (echo commands but do not execute)

    Example 1:

      %s -b fix_issue_12345 -c 35999 -p 3

      This will pull changeset 35999 patch 3, perform build and test.

    Example 2:

      %s -b another_branchname -c 35101 -B build-bootstrap

      This will pull changes set 35101 patch 1, perform build and test
      in build dir build-bootstrap.

    """ % (me, me, me)
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_dryrun, flag_echo, flag_branchname, flag_patch, flag_change
  global flag_build_dir

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "deDb:c:p:B:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))
  if args:
    usage("unknown extra args")

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-e":
      flag_echo = True
    elif opt == "-D":
      flag_dryrun = True
      flag_echo = True
    elif opt == "-b":
      flag_branchname = arg
    elif opt == "-B":
      flag_build_dir = arg
    elif opt == "-c":
      flag_change = int(arg)
    elif opt == "-p":
      flag_patch = int(arg)

  if not os.path.exists("gofrontend"):
    usage("expected to find gofrontend subdir")
  if not os.path.exists("gcc-trunk"):
    usage("expected to find gcc-trunk subdir")
  if not os.path.exists(flag_build_dir):
    usage("expected to find build directory %s" % flag_build_dir)


parse_args()
u.setdeflanglocale()
perform()
