#!/usr/bin/python3
"""Compares versions of personal Python scripts with git dir.

"""

import getopt
import hashlib
import os
import re
import sys

import script_utils as u

# dry run
flag_dryrun = True

# source
def_source_dir = os.path.join(os.environ["HOME"], "bin")
flag_source_dir = def_source_dir

# destination dir
def_dest_dir = "/ssd/devel-scripts"
flag_dest_dir = def_dest_dir

# copy in reverse (from dest to src)
flag_reverse = False

# files to examine (filled in at runtime)
files_to_examine = []
file_regex = re.compile(r"^\S+\.py$")

# file containing list of exceptions
exceptions_file = "ignore_for_update.txt"


def checksum_file(f):
  """Return md5sum for contents of file."""
  m = hashlib.md5()
  try:
    with open(f, "r") as rf:
      lines = rf.readlines()
      for line in lines:
        m.update(line.encode("utf-8"))
  except IOError:
    u.error("open failed for %s" % f)
  return m.hexdigest()


def examine_file(f):
  """Examine and copy a file if it needs copying."""
  rval = 0
  sfile = os.path.join(flag_source_dir, f)
  if not os.path.exists(sfile):
    u.warning("file %s does not exist in src dir -- skipping" % f)
    return 0
  dfile = os.path.join(flag_dest_dir, f)
  docopy = False
  if not os.path.exists(dfile):
    u.verbose(1, "file %s does not exist in dest dir" % f)
    docopy = True
  else:
    scksum = checksum_file(sfile)
    dcksum = checksum_file(dfile)
    if scksum != dcksum:
      u.verbose(1, "checksum mismatch (%s vs %s) "
                "on file %s" % (scksum, dcksum, f))
      docopy = True
  if docopy:
    if flag_dryrun:
      u.verbose(0, "dryrun: cp %s %s" % (sfile, dfile))
    else:
      u.verbose(0, "cp %s %s" % (sfile, dfile))
      u.docmd("cp %s %s" % (sfile, dfile))
      u.docmd("chmod 0755 %s" % dfile)
      rval = 1
  return rval


def read_exceptions():
  """Collect list of exceptions (files to not examine)."""
  ef = os.path.join(flag_source_dir, exceptions_file)
  if not os.path.exists(ef):
    ef = os.path.join(flag_dest_dir, exceptions_file)
  exceptions = {}
  if os.path.exists(ef):
    try:
      inf = open(ef, "rb")
    except IOError as e:
      u.error("internal error: unable to open "
              "exceptions file %s: %s" % (ef, e.strerror))
    lines = inf.readlines()
    inf.close()
    for line in lines:
      exceptions[line.strip()] = 1
  u.verbose(1, "exceptions: %s" % "\n".join(exceptions.keys()))
  return exceptions


def collect_files():
  """Collect files of interest from src."""
  exceptions = read_exceptions()
  for item in os.listdir(flag_source_dir):
    if file_regex.match(item) and item not in exceptions:
      files_to_examine.append(item)
  u.verbose(1, "found %d items in src dir" % len(files_to_examine))


def examine_files():
  """Look at each file."""
  total_copied = 0
  for afile in files_to_examine:
    total_copied += examine_file(afile)
  if total_copied:
    u.verbose(0, "... %d file(s) copied" % total_copied)


def perform():
  """Main driver routine."""
  collect_files()
  examine_files()


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options] <subdir>

    options:
    -d    increase debug msg verbosity level
    -D Y  set dest dir to Y
    -S X  set src dir to Y
    -C    perform copy as opposed to just identifying diffs
    -R    reverse direction of copy (update src based on dst)

    Default src: %s
    Default dst: %s

    """ % (me, def_source_dir, def_dest_dir))
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_dryrun, flag_reverse
  global flag_source_dir, flag_dest_dir

  try:
    optlist, _ = getopt.getopt(sys.argv[1:], "dD:S:CR")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-D":
      flag_dest_dir = arg
    elif opt == "-S":
      flag_source_dir = arg
    elif opt == "-C":
      flag_dryrun = False
    elif opt == "-R":
      flag_reverse = True

  if not os.path.exists(flag_source_dir):
    usage("source dir %s does not exist" % flag_source_dir)
  if not os.path.isdir(flag_source_dir):
    usage("source dir %s is not a directory" % flag_source_dir)
  if not os.path.exists(flag_dest_dir):
    usage("dest dir %s does not exist" % flag_dest_dir)
  if not os.path.isdir(flag_dest_dir):
    usage("dest dir %s is not a directory" % flag_dest_dir)
  if flag_reverse:
    flag_source_dir, flag_dest_dir = flag_dest_dir, flag_source_dir
  u.verbose(1, "src dir: %s" % flag_source_dir)
  u.verbose(1, "dst dir: %s" % flag_dest_dir)


parse_args()
u.setdeflanglocale()
perform()
