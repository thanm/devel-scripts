#!/usr/bin/python3
"""Script to cleanup merged local branches.

Given a private branch XXX, runs the following sequence of commands:

  git checkout master
  git pull
  git checkout XXX
  git rebase
  git checkout master
  git branch -d XXX

Private branches that correspond to merged commits/patches frequently
require that I use the sequence above to get rid of them.

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

# Branches to target
flag_branches = {}

# Select all branches
flag_allbranches = False

# Main branch name
flag_mainbranch = "master"


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
  return u.doscmd(cmd, nf)


def visit_branch(b):
  """Work on specified branch."""
  docmd("git checkout %s" % b)

  # Query upstream branch for this branch. If not set, then don't
  # try to work on it.
  lines = u.docmdlines("git rev-parse --symbolic-full-name --abbrev-ref @{u}", True)
  if not lines:
    u.warning("no upstream branch set for branch %s, skipping" % b)
    return
  if lines[0] != "origin/" + flag_mainbranch:
    u.warning("non-%s upstream branch of %s set for branch %s, skipping" % (flag_mainbranch, lines[0], b))
    return

  rebst = doscmd("git rebase", True)
  if not rebst:
    # rebase failed, back out
    u.warning("rebase failed...")
    docmd("git rebase --abort")
    return
  docmd("git checkout %s" % flag_mainbranch)
  doscmd("git branch -d %s" % b, True)


def perform():
  """Main driver routine."""
  global flag_branches
  # Run 'git branch'
  lines = u.docmdlines("git branch", True)
  if not lines:
    u.error("not currently in git workspace")
  reg = re.compile(r"^[\+\*\s]*(\S+)\s*$")
  # Interpret output of git branch
  branches = {}
  for line in lines:
    u.verbose(3, "line is: =%s=" % line)
    m = reg.match(line)
    if not m:
      u.error("internal error: unable to match "
              "'git branch' on: %s" % line)
    bname = m.group(1)
    if bname == flag_mainbranch:
      continue
    u.verbose(2, "capturing local branch: %s" % bname)
    branches[bname] = 1
  # Did we see branches of interest?
  if flag_branches:
    for b in flag_branches:
      if b not in branches:
        u.error("specified branch %s not present "
                "in output of 'git branch'" % b)
  if flag_allbranches:
    flag_branches = branches
  u.verbose(1, "pulling %s" % flag_mainbranch)
  docmd("git checkout %s" % flag_mainbranch)
  docmd("git pull")
  for b in flag_branches:
    visit_branch(b)


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options]

    options:
    -a    look for all branches other than main/master/release
    -e    echo commands before executing
    -d    increase debug msg verbosity level
    -D    dryrun mode (echo commands but do not execute)
    -M x  main branch name is 'x'

    """ % me)
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_echo, flag_dryrun, flag_allbranches, flag_mainbranch

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "dDeaM:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))
  for b in args:
    flag_branches[b] = 1

  for opt, optarg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-D":
      flag_dryrun = True
      flag_echo = True
    elif opt == "-e":
      flag_echo = True
    elif opt == "-M":
      u.verbose(0, "main branch set to '%s'" % optarg)
      flag_mainbranch = optarg
    elif opt == "-a":
      flag_allbranches = True
      if args:
        usage("if -a is used, don't supply branch names")
  if not flag_branches and not flag_allbranches:
    usage("supply a branch name as arg, or use -a option")

#......................................................................
#
# Main portion of script
#
parse_args()
u.setdeflanglocale()
perform()
