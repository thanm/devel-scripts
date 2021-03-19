#!/usr/bin/python3
"""Inspect path to locate possible completions for cmd.

Walk through the entries in the current PATH env var and look for
things that might match a cmd. Argument is a text string S; we dump
out any program on the path that contains S.

If SHELL is set to bash, then we also test to see if any
bash functions currently defined match S.

"""

import locale
import os
import re
import subprocess
import sys
import script_utils as u

flag_text = ""


def parse_args(argv):
  """Parse command line arguments for the script."""
  global flag_text
  inprog = 0
  pa = []
  arg = argv.pop(0)
  while argv:
    arg = argv.pop(0)
    u.verbose(3, "parse_args: arg is " + arg)
    if inprog == 1:
      pa.append(arg)
    elif arg == "-d":
      u.increment_verbosity()
      u.verbose(1, "debug level now %d" % u.verbosity_level())
    else:
      pa.append(arg)
  nargs = len(pa)
  if nargs != 1:
    u.error("supply single text string to match")
  flag_text = pa.pop()
  u.verbose(1, "+ search text: " + flag_text)


def inspect_path():
  """Inspect path components."""
  if "PATH" not in os.environ:
    u.error("no definition for PATH in environment (?)")
  path = os.environ["PATH"]
  u.verbose(1, "PATH set to: %s" % path)
  path_directories = path.split(":")
  matcher = re.compile(r"^.*%s.*$" % flag_text)
  for d in path_directories:
    u.verbose(2, "+ considering dir %s" % d)
    if os.path.isdir(d):
      for filename in os.listdir(d):
        m = matcher.match(filename)
        if m is not None:
          print("%s/%s" % (d, filename))


def shell_is_bash():
  """Return TRUE if the shell being used is bash."""
  if "SHELL" not in os.environ:
    u.warning("no definition for SHELL in environment (?)")
    return False
  shell = os.environ["SHELL"]
  u.verbose(1, "SHELL set to: %s" % shell)
  matcher = re.compile(r"^.*/bash$")
  m = matcher.match(shell)
  if m is not None:
    return True
  return False


def inspect_bash_functions():
  """Examine declared bash functions to see if any of them match."""
  cmd = "echo typeset -F | bash -i 2>&1"
  mypipe = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
  pout, perr = mypipe.communicate()
  if mypipe.returncode != 0:
    u.error("command failed (rc=%d): cmd was %s: "
            "err=%s" % (mypipe.returncode, cmd, perr))
  encoding = locale.getdefaultlocale()[1]
  decoded = pout.decode(encoding)
  lines = decoded.strip().split("\n")
  matcher = re.compile(r"^declare\s+\S+\s+(%s)\s*$" % flag_text)
  for line in lines:
    u.verbose(3, "+ considering bash declaration %s" % line)
    m = matcher.match(line)
    if m is not None:
      frag = m.group(1)
      print("bash function %s" % frag)

#----------------------------------------------------------------------
#
# Main portion of script
#
parse_args(sys.argv)
u.setdeflanglocale()
inspect_path()
if shell_is_bash():
  inspect_bash_functions()
