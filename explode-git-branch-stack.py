#!/usr/bin/python3
"""Dump out diffs for each commit on a git development branch.

For a given development branch, dump out diffs for each commit
on the branch into /tmp.  Example from git log --oneline for
hypothetical development branch 'mybranch':

  ca3b66ca8d (HEAD -> mybranch) finalthing
  51df6b49da anotherthing
  2b3ddf5180 firstthing
  7fa195c1b9 (origin/master, origin/HEAD, master) unrelated

This script will produce the following dumps:

  /tmp/item=1.branch=mybranch.commit=ca3b66ca8d.txt
  /tmp/item=2.branch=mybranch.commit=51df6b49da.txt
  /tmp/item=3.branch=mybranch.commit=2b3ddf5180.txt
  /tmp/item=4.branch=mybranch.index.txt

Also of use is the '-S' option which will explode the contents
of the stash list, instead of a branch.
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

# Tag to apply to output files.
flag_tag = None

# Files emitted
files_emitted = []

# Look at git stash, not branch
flag_dostash = False


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


def docmdout(cmd, outfile):
  """Execute a command to an output file."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmdout(cmd, outfile)


def docmdinout(cmd, infile, outfile):
  """Execute a command reading from input file and writing to output file."""
  if flag_echo:
    sys.stderr.write("executing: %s < %s > %s\n" % (cmd, infile, outfile))
  if flag_dryrun:
    return
  u.docmdinout(cmd, infile, outfile)


def process_commit(idx, flav, branchname, githash, comment):
  """Process a commit by hash."""
  global files_emitted
  tag = ""
  if flag_tag:
    tag = ".tag=%s" % flag_tag
  fn = "/tmp/item%d.%s%s%s.commit%s.txt" % (idx, flav, branchname, tag, githash)
  if flag_dryrun:
    u.verbose(0, "<dryrun: emit diff for "
              "%s^ %s to %s>" % (githash, githash, fn))
    return
  files_emitted.append(fn)
  try:
    outf = open(fn, "w")
  except IOError as e:
    u.error("unable to open %s: %s" % (fn, e.strerror))
  if comment != "":
    outf.write("// comment: %s\n" % comment)
    outf.write("//\n")
  if flav != "stash":
    lines = u.docmdlines("git log --name-only -1 %s" % githash)
    if not lines:
      u.error("empty output from 'git log --name-only -1 %s'" % githash)
    for line in lines:
      outf.write(line)
      outf.write("\n")
    outf.write("--------------------------------------------------------------\n")
  else:
    outf.write("Stash entry: %s\n" % githash)
  lines = u.docmdlines("git diff %s^ %s" % (githash, githash))
  if not lines:
    u.error("empty output from 'git diff %s^ %s'" % (githash, githash))
  for line in lines:
    outf.write(line)
    outf.write("\n")
  outf.close()
  u.verbose(1, "wrote %d diff lines to %s" % (len(lines), fn))


def emit_index_file(flav):
  """Emit index to emitted files."""
  global files_emitted
  n = len(files_emitted) + 1
  fn = "/tmp/item%d.%s.index.txt" % (n, flav)
  try:
    outf = open(fn, "w")
  except IOError as e:
    u.error("unable to open %s: %s" % (fn, e.strerror))
  outf.write("Files emitted:\n\n%s\n" % " ".join(files_emitted))
  if flav != "stash":
    outf.write("\n\nLog:\n\n")
    lines = u.docmdlines("git log --name-only -%d HEAD" % len(files_emitted))
    for line in lines:
      outf.write(line)
      outf.write("\n")
  outf.close()
  u.verbose(0, "... index file emitted to %s\n" % fn)


def perform_on_stash():
  """Main driver routine for -S case."""
  lines = u.docmdlines("git stash list")
  if not lines:
    u.warning("no stash entries found, leaving now.")
    return
  streg = re.compile(r"^(stash@{\S+})\:\s.+$")
  idx = 0
  for line in lines:
    idx += 1
    m = streg.match(line)
    if not m:
      u.error("can't pattern match output of git stash list: %s" % line)
    stname = m.group(1).strip()
    u.verbose(1, "examining stash entry: %s" % stname)
    process_commit(idx, "stash", "stash", stname, "")
  emit_index_file("stash")


def perform():
  """Main driver routine."""
  if flag_dostash:
    perform_on_stash()
    return

  lines = u.docmdlines("git status -sb")
  if not lines:
    u.error("empty output from git status -sb")
  brnreg = re.compile(r"^## (\S+)\.\.(\S+) \[ahead (\d+)\]\s*$")
  m = brnreg.match(lines[0])
  if not m:
    u.error("can't pattern match output of git status -sb: %s" % lines[0])
  branchname = m.group(1).strip(".")
  commits = int(m.group(3))
  u.verbose(1, "branch is: %s commits: %d" % (branchname, commits))

  # Grab info on commits
  lines = u.docmdlines("git log --oneline -%d" % commits)
  if not lines:
    u.error("empty output from 'git log --oneline'")

  # Process commits in reverse order
  creg = re.compile(r"^(\S+) (\S.+)$")
  lines.reverse()
  idx = 0
  for cl in lines:
    idx += 1
    m = creg.match(cl)
    if not m:
      u.error("can't pattern match git log output: %s" % cl)
    githash = m.group(1)
    comment = m.group(2)
    u.verbose(1, "processing hash %s comment %s" % (githash, comment))
    process_commit(idx, "branch", branchname, githash, comment)

  emit_index_file("branch=%s" % branchname)


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options]

    options:
    -t T  tag output files with tag T
    -e    echo commands before executing
    -d    increase debug msg verbosity level
    -D    dryrun mode (echo commands but do not execute)
    -S    examine contents of stash, not a branch

    This program walks the stack of commits for a given git
    development branch and dumps out diffs for each commit
    into /tmp.

    Example 1: examine current branch

    %s

    Example 2: examine stash

    %s -S



    """ % (me, me, me))

  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_echo, flag_dryrun, flag_tag, flag_dostash

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "deDSt:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  if args:
    usage("unknown extra args: %s" % " ".join(args))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-S":
      flag_dostash = True
    elif opt == "-D":
      u.verbose(0, "+++ dry run mode")
      flag_dryrun = True
      flag_echo = True
    elif opt == "-e":
      flag_echo = True
    elif opt == "-t":
      flag_tag = arg


#......................................................................
#
# Main portion of script
#
parse_args()
u.setdeflanglocale()
perform()
exit(0)
