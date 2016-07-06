#!/usr/bin/python
"""Install a 'blob' file from an extract shell archive.

This script installs the 3rd party blob contained in a previously
downloaded extract-*.sh file. This avoids the need to have to page
through and accept the user agreement (which is what you have to do if
you execute the archive directly).

"""

import locale
import os
import re
import subprocess
import sys
import script_utils as u


#......................................................................

me = sys.argv[0]
mebase = os.path.basename(me)

if len(sys.argv) != 2:
  u.error("%s: supply exactly one argument" % mebase)

arg = sys.argv[1]

if not re.compile(r"extract\-.+\.sh$").match(arg):
  u.warning("arg '%s' does not match template extract*.sh" % arg)

if not os.path.exists(arg):
  u.error("unable to access file arg '%s'" % arg)

u.verbose(0, "... examining '%s'" % arg)
matcher = re.compile(r"tail \-n \+\d+ .+ tar zxv")
cmd = ""
encoding = locale.getdefaultlocale()[1]
with open(arg, "rb") as fin:
  for line in fin:
    decoded = line.decode(encoding)
    if matcher.match(decoded):
      # found
      cmd = re.sub(r"\$0", arg, decoded.rstrip())
      break

if not cmd:
  u.error("could not locate tail/tar line with proper form in '%s'" % arg)

u.verbose(0, "... extracting files from '%s'" % arg)
rc = subprocess.call(cmd, shell=True)
if rc != 0:
  u.error("error: cmd failed: %s" % cmd)
