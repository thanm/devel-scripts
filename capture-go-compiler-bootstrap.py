#!/usr/bin/python3
"""Script to capture/benchmark Go compiler bootstrap.

This script mimics the actions taken by "go tool dist bootstrap" to
capture the Go build trace for building the Go compiler.

Background: when you run "make.bash" in a regular Go repository, it
does a build of a set of things in <goroot>/src/cmd, including
the compiler and linker.

Script expects to be run in a GOROOT; it will perform its work
in the <goroot>/pkg subdir, as with the regular Go bootstrap build.

Output
- script that will replay the compile, with appropriate
  hooks set for pprof or perf profiles

"""

import getopt
import os
import re
import shutil
import sys
import tempfile

import script_utils as u

# Echo command before executing
flag_echo = True

# Dry run mode
flag_dryrun = False


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


def docmderrout(cmd, outfile):
  """Execute a command."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmderrout(cmd, outfile)


def docmdout(cmd, outfile):
  """Execute a command to an output file."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmdout(cmd, outfile)


def docmderrout(cmd, outfile):
  """Execute a command to an output file capturing stderr."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmderrout(cmd, outfile)


def copydir(src, dst):
  """Copy directory."""
  if flag_echo:
    sys.stderr.write("copying dir %s to dir %s\n" % (src, dst))
  if flag_dryrun:
    return
  shutil.copytree(src, dst)


def rmdir(src):
  """Remove directory."""
  if flag_echo:
    sys.stderr.write("removing dir %s\n" % src)
  if flag_dryrun:
    return
  shutil.rmtree(src)


def rmfile(afile):
  """Remove a file."""
  if flag_echo:
    sys.stderr.write("removing file %s\n" % afile)
  if flag_dryrun:
    return
  os.unlink(afile)


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


def dormdir(thedir):
  """Remove dir."""
  if flag_echo:
    sys.stderr.write("rm -r " + thedir + "\n")
  if flag_dryrun:
    return
  if not os.path.exists(thedir):
    return
  try:
    rmdir(thedir)
  except OSError as err:
    u.error("rmdir(%s) failed: %s" % (thedir, err))




def perform():
  """Main driver routine."""

  # Preamble
  here = os.getcwd()
  workspace = os.path.join(here, "pkg/bootstrap")

  # Clean
  docmd("go clean -cache")
  rmdir(os.path.join(workspace, "pkg"))
  docmd("mkdir %s" % os.path.join(workspace, "pkg"))
  docmd("go clean -cache")

  # Environment setup
  os.environ["GOPATH"] = workspace

  # Perform
  dochdir(workspace)
  transcript = "/tmp/transcript.txt"
  u.verbose(0, "... kicking off build")
  docmderrout("go build -x -work -tags math_big_pure_go "
              "bootstrap/cmd/compile/... ", transcript)

  # Post-process
  outscript = "/tmp/buildscript.sh"
  u.verbose(0, "... post-processing")
  doscmd("capture-go-compiler-invocation.py "
           "-N -A -C -i %s -o %s" % (transcript, outscript))
  u.verbose(0, "... done: final script is %s" % outscript)


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options]

    options:
    -e    echo commands before executing
    -d    increase debug msg verbosity level
    -D    dryrun mode (echo commands but do not execute)

    Example usage:

    $ cd /my/go/root
    $ %s

    The command above will:
    - perform a bootstrap build of the Go compiler within
      <goroot/pkg/bootstrap>, capturing the output of "go build -x"
    - rewrite the build transcript into a script that can be
      used to profile the bootstrap compiler

    """ % (me, me))

  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_echo, flag_dryrun

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "deD")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  if args:
    usage("unknown extra args: %s" % " ".join(args))

  for opt, _ in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-D":
      u.verbose(0, "+++ dry run mode")
      flag_dryrun = True
      flag_echo = True
    elif opt == "-e":
      flag_echo = True

  # Check to make sure we're in a goroot
  dirs = ["./src/cmd/compile/internal/ssa",
          "./src/cmd/go/internal/work/build.go"]
  for d in dirs:
    if not os.path.exists(d):
      usage("unable to locate %s (not in GOROOT?)" % d)

  # Check to make sure there is an existing bootstrap dir
  dirs = ["./pkg/bootstrap/bin",
          "./pkg/bootstrap/src",
          "./pkg/bootstrap/pkg"]
  for d in dirs:
    if not os.path.exists(d):
      usage("unable to locate %s (please run make.bash to prepopulate?)" % d)


#......................................................................
#
# Main portion of script
#
parse_args()
u.setdeflanglocale()
perform()
exit(0)
