#!/usr/bin/python
"""Script to invoke emacs on currently branched files in a git repo.

Invokes Emacs on the current set of files in a private branch.
Sets GOROOT if this looks like a GO root repository.

"""

import getopt
import os
import re
import sys

import script_utils as u


# Echo command before executing
flag_echo = True

# Dry run mode
flag_dryrun = False

# Branches of interest
flag_branchname = None



def docmd(cmd):
  """Execute a command."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmd(cmd)


def doscmd(cmd, nf=None):
  """Execute a command."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.doscmd(cmd, nf)


def perform():
  """Main driver routine."""
  if not ingitrepo():
    usage("not within git repo")
  branch, modifications, untracked, renames, rev_renames = u.get_git_status()
  if flag_branchname != branch:
    if modifications or renames:
      u.error("working copy has modifications, can't proceed")
    docmd("git checkout %s" % flag_branchname)
  allfiles = {}
  for f in rev_renames:
    allfiles[f] = 1
  for f in modifications:
    allfiles[f] = 1
  doscmd("


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options]

    options:
    -b B  switch to branch B from master before starting emacs
    -e    echo commands before executing
    -d    increase debug msg verbosity level
    -D    dryrun mode (echo commands but do not execute)

    """ % me
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_echo, flag_dryrun, flag_branchname

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "dDeb:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))
  for b in args:
    flag_branches[b] = 1

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-D":
      flag_dryrun = True
      flag_echo = True
    elif opt == "-e":
      flag_echo = True
    elif opt == "-b":
      flag_branchname = arg

#
#......................................................................
#
# Main portion of script
#
parse_args()
u.setdeflanglocale()
perform()
