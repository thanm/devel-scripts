#!/usr/bin/python3
"""Patch repo for gccgo benchmarking.

Helper script for patching a Go repo in preparation for building
"compile" using gccgo. Changes the build tool to use a specific set
of flags.
"""

import getopt
import os
import re
import sys

import script_utils as u

flag_repo = None
flag_pflags = None
flag_addmx = None


def perform(repo, flags):
  """Patch specified repo."""
  u.verbose(1, "repo: %s flags: '%s'" % (repo, flags))
  rc = u.docmdnf("grep -q gccgoflags %s/src/cmd/dist/buildtool.go" % repo)
  if rc == 0:
    u.verbose(1, "src/cmd/dist/buildtool.go already patched")
    return
  # Remove any version file if it exists.
  vfile = os.path.join(repo, "VERSION")
  if os.path.exists(vfile):
    os.unlink(vfile)
  # Mangle build flags.
  regex = re.compile(r"^.+gcflags=.+$")
  oldf = "%s/src/cmd/dist/buildtool.go" % repo
  newf = "%s/src/cmd/dist/buildtool.go.patched" % repo
  try:
    with open(newf, "w") as wf:
      try:
        with open(oldf, "r") as rf:
          lines = rf.readlines()
          for line in lines:
            if regex.match(line):
              comps = line.split()
              newcomps = []
              for c in comps:
                if c == "\"-gcflags=-l\",":
                  u.verbose(0, "patching gcflags line\n")
                  newcomps.append("\"-gccgoflags=%s\", " % flags)
                  newcomps.append("\"-p=8\", ")
                  if flag_addmx:
                    newcomps.append("\"-x\", ")
                newcomps.append(c)
              line = " ".join(newcomps)
              line += "\n"
            wf.write(line)
      except IOError:
        u.verbose(0, "open failed for %s" % oldf)
  except IOError:
    u.verbose(0, "open failed for %s" % newf)
  u.verbose(1, "mv %s %s" % (newf, oldf))
  u.docmd("mv %s %s" % (newf, oldf))


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options] -r repo -f <flags>

    options:
    -d     increase debug msg verbosity level
    -r D   path to repo to patch is D
    -f S   patch build with flags in string S
    -x     add -x to patched build flags

    """ % me)

  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_repo, flag_pflags, flag_addmx

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "xdr:f:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  if args:
    usage("unknown extra args: %s" % " ".join(args))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-x":
      flag_addmx = True
    elif opt == "-r":
      if not os.path.exists(arg):
        usage("can't access -A argument %s" % arg)
      flag_repo = arg
    elif opt == "-f":
      flag_pflags = arg.split(",")

  if not flag_pflags:
    usage("no -f option specified")
  if not flag_repo:
    usage("no -r option specified")

#
#......................................................................
#
# Main portion of script
#
parse_args()
u.setdeflanglocale()
perform(flag_repo, " ".join(flag_pflags))
exit(0)
