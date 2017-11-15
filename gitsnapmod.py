#!/usr/bin/python
"""Creates a backup snapshot of a modified git repo.

Snapshots the modified files in a git repo. Data saved include copies
of the files, predecessor versions, diff for each file, and a git
patch.

"""

import getopt
import os
import re
import sys

import script_utils as u

# dry run
flag_dryrun = False

# destination directory
flag_destdir = None

# key is file, value is M/A/D
modifications = {}

# key is old file, val is new file
renames = {}

# key is new file, val is old file
rev_renames = {}

# sha for most recent commit
current_sha = None

# For -S option
flag_oldsha = None
flag_newsha = None

# For -B option
flag_branch_to_diff = None


def docmd(cmd):
  """Execute a command."""
  if flag_dryrun or u.verbosity_level() > 0:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmd(cmd)


def docmdout(cmd, outfile, nf=None):
  """Execute a command redirecting output to a file."""
  if flag_dryrun or u.verbosity_level() > 0:
    sys.stderr.write("executing: " + cmd + " > " + outfile + "\n")
  if flag_dryrun:
    return
  return u.docmdout(cmd, outfile, nf)


def collect_modfiles():
  """Collect modified files."""
  if flag_oldsha:
    stcmd = ("git diff --name-status "
             "%s..%s" % (flag_oldsha, flag_newsha))
  elif flag_branch_to_diff:
    # Check if any diffs
    mb = "master %s" % flag_branch_to_diff
    rc = u.docmdnf("git diff --quiet %s" % mb)
    if rc == 0:
      u.error("unable to proceed -- no diffs "
              "between branches %s" % mb)
    stcmd = ("git diff --name-status %s" % mb)
  else:
    stcmd = "git status -s"
  u.verbose(1, "modfiles git cmd: %s" % stcmd)
  lines = u.docmdlines(stcmd)
  rs = re.compile(r"^\s*$")
  rb = re.compile(r"^\S+\.~\d+~$")
  r1 = re.compile(r"^(\S+)\s+(\S+)$")
  r2 = re.compile(r"^(\S+)\s+(\S+) \-\> (\S+)$")
  for line in lines:
    u.verbose(2, "git status line: +%s+" % line.strip())
    ms = rs.match(line)
    if ms:
      continue
    m1 = r1.match(line)
    if m1:
      op = m1.group(1)
      modfile = m1.group(2)
      if op == "AM" or op == "MM" or op == "??":
        if rb.match(modfile):
          continue
        u.error("found modified or untracked "
                "file %s -- please run git add ." % modfile)
      if op != "A" and op != "M" and op != "D":
        u.error("internal error: bad op %s in git "
                "status line %s" % (op, line.strip()))
      if modfile in modifications:
        u.error("internal error: mod file %s "
                "already in table" % modfile)
      modifications[modfile] = op
      continue
    m2 = r2.match(line)
    if m2:
      op = m2.group(1)
      oldfile = m2.group(2)
      newfile = m2.group(3)
      if op == "RM":
        u.error("found modified file %s -- please run git add ." % newfile)
      if oldfile in modifications:
        u.error("internal error: src rename %s "
                "already in modifications table" % oldfile)
      if oldfile in renames:
        u.error("internal error: src rename %s "
                "already in modifications table" % oldfile)
      if op == "R":
        renames[oldfile] = newfile
        rev_renames[newfile] = oldfile
        if newfile in modifications:
          u.error("internal error: dest of rename %s "
                  "already in modifications table" % newfile)
        renames[oldfile] = newfile
        rev_renames[newfile] = oldfile
        modifications[newfile] = "M"
      else:
        u.error("internal error: unknown op %s "
                "in git status line %s" % (op, line))
      continue
    u.error("internal error: pattern match failed "
            "for git status line %s" % line)


def emit_deletions_and_renames():
  """Emit record of deletions and renames."""
  deletions = {}
  for afile, op in modifications.iteritems():
    if op == "D":
      deletions[afile] = 1
  if deletions:
    outf = "%s/DELETIONS" % flag_destdir
    if flag_dryrun:
      u.verbose(0, "emitting record of deletions to %s" % outf)
    else:
      with open(outf, "w") as wf:
        for todel in deletions:
          wf.write("%s\n" % todel)
  if renames:
    outf = "%s/RENAMES" % flag_destdir
    if flag_dryrun:
      u.verbose(0, "emitting record of renames to %s" % outf)
    else:
      with open(outf, "w") as wf:
        for oldfile, newfile in renames.iteritems():
          wf.write("%s -> %s\n" % (oldfile, newfile))


def copy_file(srcf, destf):
  """Copy a file."""
  if not os.path.exists(srcf):
    u.error("unable to copy src file %s: doesn't exist" % srcf)
  ddir = os.path.dirname(destf)
  if not os.path.exists(ddir):
    docmd("mkdir -p %s" % ddir)
  docmd("cp %s %s" % (srcf, destf))


def emit_modified_files():
  """Archive copies of added/modified files."""
  showsha = current_sha
  nf = 0
  if flag_oldsha:
    showsha = flag_oldsha
  for afile, op in modifications.iteritems():
    if op == "A" or op == "M":
      copy_file(afile, "%s/%s" % (flag_destdir, afile))
      nf += 1
    if op == "M":
      toshow = afile
      if afile in rev_renames:
        toshow = rev_renames[afile]
      docmdout("git show -M %s:%s" % (showsha, toshow),
               "%s/%s.BASE" % (flag_destdir, afile))
  return nf


def grab_current_sha():
  """Grab current sha for repo."""
  global current_sha
  lines = u.docmdlines("git log --no-abbrev-commit --pretty=oneline -1")
  ar = lines[0].split()
  current_sha = ar[0]
  u.verbose(1, "current sha: %s" % current_sha)


def archive():
  """Archive modifications."""
  if flag_oldsha:
    dcmd = "git diff %s..%s" % (flag_oldsha, flag_newsha)
  elif flag_branch_to_diff:
    dcmd = "git diff %s master" % flag_branch_to_diff
  else:
    dcmd = "git diff --cached"
  docmdout(dcmd, "%s/git.diff.txt" % flag_destdir)
  docmdout("git log -10", "%s/git.log10.txt" % flag_destdir)
  grab_current_sha()
  emit_deletions_and_renames()
  nf = emit_modified_files()
  u.verbose(0, "... diff, log, and %d files copied" % nf)


def usage(msgarg=None):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options] -o <destdir>

    options:
    -h       print this help message
    -d       increase debug msg verbosity level
    -o D     write backup files to dest dir D
    -D       dry run (echo cmds but do not execute)
    -S X:Y   derive list of files with changes between
             commits with shas X + Y (where X is the older sha)
    -B X     derive list of files from comparing branch X
             to branch 'master'

    """ % me
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_dryrun, flag_destdir
  global flag_oldsha, flag_newsha, flag_branch_to_diff

  try:
    optlist, _ = getopt.getopt(sys.argv[1:], "hdo:DS:B:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-h":
      usage()
    elif opt == "-D":
      flag_dryrun = True
    elif opt == "-B":
      flag_branch_to_diff = arg
    elif opt == "-S":
      r1 = re.compile(r"^(\S+):(\S+)$")
      m1 = r1.match(arg)
      if m1:
        flag_oldsha = m1.group(1)
        flag_newsha = m1.group(2)
        u.verbose(1, "old sha: %s" % flag_oldsha)
        u.verbose(1, "new sha: %s" % flag_newsha)
      else:
        u.usage("malformed -S argument %s (should be of form X:Y)" % arg)
    elif opt == "-o":
      if flag_destdir:
        usage("specify a single dest dir with -o")
      if not os.path.exists(arg):
        usage("dest dir %s does not exist" % arg)
      if not os.path.isdir(arg):
        usage("dest dir %s is not a directory" % arg)
      not_empty = False
      for _ in os.listdir(arg):
        not_empty = True
        break
      if not_empty:
        u.warning("warning: dest dir %s is not empty" % arg)
      flag_destdir = arg
  if not flag_destdir:
    usage("supply dest dir with -o option")
  if flag_branch_to_diff and flag_oldsha:
    usage("supply either -B or -S but not both")
  u.verbose(1, "dst dir: %s" % flag_destdir)


parse_args()
u.setdeflanglocale()
collect_modfiles()
archive()
