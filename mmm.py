#!/usr/bin/python
"""Run equivalent of 'mmm <dir>'.

"""

import getopt
import os
import re
import sys

import script_utils as u

# dry run
flag_dryrun = False

# subdir in which to perform make
flag_subdir = None

# run under strace
flag_strace = ""

# add showcommands
flag_showcommands = ""

# top level make
flag_toplevel = False

# pass -k to make
flag_dashk = ""

# build dependencies
flag_dependencies = False

# additional make args for top level make
flag_extra_make_args = []

# Issue jack-admin cmds?
flag_use_jack = False

# Make checkbuilds
flag_checkbuild = False

# Parallel factor
flag_parfactor = 40


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options] <subdir>

    options:
    -d    increase debug msg verbosity level
    -s    add 'showcommands' to make invocation
    -S    run under strace (output to strace.txt)
    -D    dry run (echo cmds but do not execute)
    -t    simulate top level make (equivalent of "m")
    -T    simulate checkbuild (equivalent of "make checkbuild")
    -a    simulate make with dependencies (equivalent of "mmma")
    -x A  add extra make arg A (for top level make)
    -j N  set parallel build factor to N
    -k    pass -k when invoking make

    Example 1: rebuild art (no deps)

     %s art

    Example 2: rebuild system image (no deps)

     %s -t -x systemimage-nodeps

    Example 3: rebuild boot image (no deps)

     %s -t -x bootimage-nodeps


    """ % (me, me, me, me)
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_subdir, flag_strace, flag_toplevel, flag_dryrun
  global flag_showcommands, flag_dependencies, flag_parfactor
  global flag_dashk, flag_checkbuild

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "adkstTDSx:j:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-s":
      flag_showcommands = " showcommands"
    elif opt == "-k":
      flag_dashk = "-k"
    elif opt == "-a":
      flag_dependencies = True
    elif opt == "-S":
      flag_strace = "strace -f -o trace.txt "
    elif opt == "-D":
      flag_dryrun = True
    elif opt == "-t":
      flag_toplevel = True
    elif opt == "-T":
      flag_toplevel = True
      flag_checkbuild = True
    elif opt == "-x":
      u.verbose(0, "adding extra make arg %s" % arg)
      flag_extra_make_args.append(arg)
    elif opt == "-j":
      flag_parfactor = int(arg)

  if not flag_toplevel:
    if not args:
      usage("supply dirname arg")
    if len(args) != 1:
      usage("supply single dirname arg")
    if flag_extra_make_args:
      usage("-x option can only be supplied with -t")
    flag_subdir = args[0]
  else:
    if flag_dependencies:
      usage("specify at most one of -t, -a")


parse_args()
u.setdeflanglocale()
if not flag_toplevel and not flag_dependencies:
  mkfile = os.path.join(flag_subdir, "Android.mk")
  if not os.path.exists(mkfile):
    u.error("can't access %s" % mkfile)
  os.environ["ONE_SHOT_MAKEFILE"] = mkfile
  if flag_dryrun:
    u.verbose(0, "setting os.environ[\"ONE_"
              "SHOT_MAKEFILE\"] to %s" % mkfile)

if not flag_dryrun:
  rc = u.doscmd("which jack-admin", nf=True)
  if rc == 0:
    flag_use_jack = True
    u.doscmd("jack-admin start-server")

here = os.getcwd()
am = "all_modules"
if flag_toplevel:
  am = ""
  if flag_extra_make_args:
    am = " %s" % " ".join(flag_extra_make_args)
  if flag_checkbuild:
    am += " checkbuild"
elif flag_dependencies:
  am = "MODULES-IN-%s" % re.sub("/", "-", flag_subdir)
cmd = ("%smake %s -j%d -C %s -f build/core/main.mk "
       "%s%s" % (flag_strace, flag_dashk, flag_parfactor, here, am, flag_showcommands))
u.verbose(0, "cmd is: %s" % cmd)
rc = 0
if not flag_dryrun:
  rc = u.docmdnf(cmd)
if not flag_dryrun and flag_use_jack:
  u.doscmd("jack-admin stop-server")
if rc != 0:
  u.error("** build failed, command was: %s" % cmd)
