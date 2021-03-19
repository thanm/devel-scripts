#!/usr/bin/python3
"""Graphical diff of svn working copy file against predecessor.

Determine svn predecessor of specified file and run 'meld' to compare
against it. If file modified, compare working copy against checked in copy.
If file not modified, then compare against previous version.

"""

import getopt
import os
import re
import string
import sys
import tempfile

import script_utils as u


# File to diff
flag_target_file = ""

# Previous revision
flag_prev_revision = None

# Revision pair
flag_revision_pair = None

# Save temps if set
flag_save_temps = False

# Diff command
flag_diff_cmd = "meld"

# Set to True if specified target file is a URL
target_is_url = False


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s" % msgarg)
  print("""\
    usage:  %s [options] <file or URL>

    options:
    -d      increase debug verbosity level
    -r N    diff against previous version N
    -R M:N  diff revisions M and N for file (N can be set to PREV)
    -c C    use diff command C
    -s      save any temp files generated

    Note that use of URLs requires -R option.

    """ % os.path.basename(sys.argv[0]))
  sys.exit(1)


def parse_args():
  """Parse command line arguments for the script."""
  global flag_target_file, flag_prev_revision, target_is_url
  global flag_revision_pair, flag_diff_cmd, flag_save_temps

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "dsr:R:c:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
      u.verbose(1, "debug level now %d" % u.verbosity_level())
    elif opt == "-r":
      flag_prev_revision = int(arg)
    elif opt == "-s":
      flag_save_temps = True
    elif opt == "-c":
      flag_diff_cmd = arg
    elif opt == "-R":
      plist = arg.split(":")
      if plist[1] == "PREV":
        lr = int(plist[0])
        p = (lr, lr-1)
      else:
        p = (int(plist[0]), int(plist[1]))
      if p[0] <= 0:
        usage("specify positive left revision with -R")
      if p[1] <= 0:
        usage("specify positive right revision with -R")
      if p[0] == p[1]:
        usage("specify different revisions with -R")
      u.verbose(1, "revision pair: %d %d" % (p[0], p[1]))
      flag_revision_pair = p

  if not args or len(args) != 1:
    u.error("supply single file to diff")
  flag_target_file = args[0]
  um = re.compile(r"^.+://.+$")
  res = um.match(flag_target_file)
  if res:
    target_is_url = True
    if not flag_revision_pair:
      usage("URL target can only be used with -R option.")
  else:
    if not os.path.exists(flag_target_file):
      u.error("target file %s does not appear to exist" % flag_target_file)
    if not os.path.isfile(flag_target_file):
      u.error("target file %s is not a file" % flag_target_file)



def get_pred_revision_and_modified():
  """Run svn status to determine pred revision, modified."""
  if target_is_url:
    return (False, -1)
  lines = u.docmdlines("svn status -v %s" % flag_target_file)
  match1 = re.compile(r"^M\S*\s+\d+\s+(\d+)\s+\S+\s+\S+$")
  match2 = re.compile(r"^\s*\d+\s+(\d+)\s+\S+\s+(\S+)$")
  for line in lines:
    m = match1.match(line)
    if m:
      # file modified -- return current rev
      pversion = int(m.group(1))
      u.verbose(1, "file modified: returning (True,%d)" % pversion)
      return (True, pversion)
    m = match2.match(line)
    if m:
      # file unmodified -- return pred rev
      pversion = int(m.group(1))
      u.verbose(1, "file unmodified: returning (False,%d)" % (pversion - 1))
      return (False, pversion - 1)
    u.error("internal error: can't interpret svn status line:\n%s" % line)
  return (False, -1)


def scrub_filename(srcfile):
  """Scrub src file path (remove /, etc)."""
  srcfile = re.sub("/", "_", srcfile)
  srcfile = re.sub("\\\\", ":", srcfile)
  whitelist = ".-_=:%s%s" % (string.ascii_letters, string.digits)
  srcfile = "".join(c for c in srcfile if c in whitelist)
  return srcfile


def save_temps(tfile, revision):
  """Save copy of temp file."""
  scrubbed = scrub_filename(flag_target_file)
  savepath = "/tmp/R%d.%s" % (revision, scrubbed)
  u.docmd("cp %s %s" % (tfile.name, savepath))
  u.verbose(0, "... saved revision %d copy of "
            "%s into %s" % (revision, flag_target_file, savepath))


def perform_diff():
  """Perform graphical diff."""
  (modified, rightrev) = get_pred_revision_and_modified()
  ltf = None
  leftname = None
  if flag_prev_revision:
    rightrev = flag_prev_revision
  if flag_revision_pair:
    if modified:
      u.warning("warning: working copy of %s is "
                "modified" % flag_target_file)
    leftrev = flag_revision_pair[0]
    rightrev = flag_revision_pair[1]
    ltf = tempfile.NamedTemporaryFile(mode="w",
                                      prefix="svnpreddifftmp_REV%s_" % leftrev,
                                      delete=True)
    leftname = ltf.name
    u.verbose(1, "left temp file is: %s" % leftname)
    u.docmdout("svn cat -r%d %s" % (leftrev, flag_target_file), leftname)
    if flag_save_temps:
      save_temps(ltf, leftrev)
  else:
    u.verbose(1, "left file is: %s" % flag_target_file)
    leftname = flag_target_file
  rtf = tempfile.NamedTemporaryFile(mode="w",
                                    prefix="svnpreddifftmp_REV%s_" % rightrev,
                                    delete=True)
  rightname = rtf.name
  u.verbose(1, "right temp file is: %s" % rightname)
  u.docmdout("svn cat -r%d %s" % (rightrev, flag_target_file), rightname)
  if flag_save_temps:
    save_temps(rtf, rightrev)
  # Perform diff
  u.docmd("%s %s %s" % (flag_diff_cmd, leftname, rightname))


#----------------------------------------------------------------------
#
# Main portion of script
#
parse_args()
u.setdeflanglocale()
perform_diff()
