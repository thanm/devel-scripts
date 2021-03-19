#!/usr/bin/python3
"""Utility for preserving/restoring mod times on CMakeLists.txt files.

This utility is design to increase productive developer time when
working "stacks" of git commits in LLVM (or some other cmake-based
software corpus).

Let's say that you have a large commit stack that includes (somewhere
in it) a cmakefile modification (this doesn't seem to unusual). When
you run an interactive git rebase to update a commit that is below the
cmake mod in the stack, the process of doing the rebase will update
the file modification time of the cmake file, which will force a cmake
rerun (which is time consuming). If you as a developer know that the
change you are making is cmake-neutral, it's nice to avoid that
overhead.

The script runs in two modes: "pre" and "post" rebase. In "pre" mode, it locates
all cmakefiles (*.cmake, CMakeLists.txt) findable from the current directory,
then captures their state in a /tmp directory. It then records the temp
dir name in a file .cmake.mtime.token. In "post" mode, it restores the
mtimes of said cmake files based on the times in the saved temp dir.
"""

import getopt
import os
import re
import sys

import script_utils as u

# dry run
flag_dryrun = False

# mode
flag_mode = None

# destination directory
flag_tokenfile = ".cmake.mtime.token"

# Don't clean up if set
flag_noclean = False

# paths of cmakefiles found
cmakefiles = {}


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


def restore_mtimes():
  """Restore mtimes from tokenfile."""
  u.verbose(1, "reading token file %s" % flag_tokenfile)
  restored = 0
  try:
    with open(flag_tokenfile, "r") as tf:
      pat = re.compile(r"^\s*(\S+)\s+(\d+)\s+(\d+)\s*$")
      lines = tf.readlines()
      for line in lines:
        m = pat.match(line)
        if not m:
          u.error("pattern match failed on token file line %s" % line)
        f = m.group(1)
        st = os.stat(f)
        u.verbose(2, "before restore for %s, at=%d "
                  "mt=%d" % (f, st.st_atime, st.st_mtime))
        mt = int(m.group(2))
        at = int(m.group(3))
        newtimes = (at, mt)
        os.utime(f, newtimes)
        u.verbose(2, "restoring at=%d mt=%d for %s" % (at, mt, f))
        st = os.stat(f)
        u.verbose(2, "after restore for %s, at=%d "
                  "mt=%d" % (f, st.st_atime, st.st_mtime))
        restored += 1
  except IOError:
    u.error("unable to read token file %s" % flag_tokenfile)
  return restored


def cleanup():
  """Remove token."""
  if flag_dryrun:
    u.verbose(0, "removing %s" % flag_tokenfile)
  if flag_noclean:
    u.verbose(0, "skipping cleanup since -S specified")
    return
  else:
    os.unlink(flag_tokenfile)


def find_cmakefiles():
  """Locate files to consider."""
  if cmakefiles:
    return
  lines = u.docmdlines("find . -name \"*.cmake\" -print "
                       "-o -name CMakeLists.txt -print")
  for line in lines:
    f = line.strip()
    if not f:
      continue
    u.verbose(2, "adding %s to cmakefiles" % f)
    cmakefiles[f] = 1


def create_token():
  """Deposit token file."""
  u.verbose(0, "creating token %s" % flag_tokenfile)
  try:
    with open(flag_tokenfile, "w") as tf:
      for f in sorted(cmakefiles):
        st = os.stat(f)
        u.verbose(2, "storing %s at=%d mt=%d "
                  "to token" % (f, st.st_atime, st.st_mtime))
        tf.write("%s %d %d\n" % (f, st.st_atime, st.st_mtime))
  except IOError:
    u.error("unable to write to %s" % flag_tokenfile)


def perform_post():
  """Driver for 'post' mode."""
  u.verbose(1, "starting 'post' mode")
  nr = restore_mtimes()
  cleanup()
  u.verbose(1, "'post' mode complete")
  u.verbose(0, "... mtimes for %d cmake files restored" % nr)


def perform_pre():
  """Driver for 'pre' mode."""
  u.verbose(1, "starting 'pre' mode")
  find_cmakefiles()
  if not cmakefiles:
    u.error("no cmake files found -- nothing to do")
  create_token()
  u.verbose(1, "'pre' mode complete")
  u.verbose(0, "... %d cmake files archived, state "
            "written to %s" % (len(cmakefiles), flag_tokenfile))


def usage(msgarg=None):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options] <mode>

    where <mode> is either "pre" or "post"

    options:
    -h       print this help message
    -d       increase debug msg verbosity level
    -D       dry run (echo cmds but do not execute)
    -F C     don't run 'find', but instead operate only on file C
    -S       skip cleanup of token/tempfile in post mode

    """ % me)
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_dryrun, flag_mode, flag_noclean

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "hdDSF:")
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
    elif opt == "-S":
      flag_noclean = True
    elif opt == "-F":
      if os.path.exists(arg):
        u.verbose(0, "adding %s to cmakefiles dict" % arg)
        cmakefiles[arg] = 1
      else:
        u.error("-F arg %s doesn't seem to exist" % arg)

  # Check for mode
  if len(args) != 1:
    usage("supply a single mode argument (either 'pre' or 'post')")
  if args[0] == "pre":
    flag_mode = "pre"
  elif args[0] == "post":
    flag_mode = "post"
  else:
    usage("unknown mode argument %s" % args[0])


parse_args()
u.setdeflanglocale()
if flag_mode == "pre":
  perform_pre()
else:
  perform_post()
