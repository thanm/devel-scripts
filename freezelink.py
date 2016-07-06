#!/usr/bin/python
"""Resolve a symbolic link to a real file."""

import getopt
import os
import sys

import script_utils as u

flag_infiles = []


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options] link1 link2 ... linkN

    options:
    -d    increase debug msg verbosity level

    """ % os.path.basename(sys.argv[0])
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_infiles

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "d")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))
  if not args:
    usage("supply one or more link paths as arguments")

  for opt, _ in optlist:
    if opt == "-d":
      u.increment_verbosity()
  for a in args:
    if not os.path.exists(a):
      u.warning("failed to open/access '%s' -- skipping" % a)
    else:
      try:
        p = os.readlink(a)
      except OSError as ose:
        u.warning("unable to process '%s' -- %s" % (a, ose))
        continue
      flag_infiles.append(a)


# Setup
u.setdeflanglocale()
parse_args()
here = os.getcwd()
for link in flag_infiles:
  targ = os.readlink(link)
  os.chdir(here)
  dn = os.path.dirname(link)
  bn = os.path.basename(link)
  if dn:
    u.verbose(1, "changing to dir %s" % dn)
    os.chdir(dn)
  if os.path.isdir(targ):
    u.warning("target of link %s is a directory, skipping" % link)
    continue
  u.verbose(1, "copying %s to %s" % (targ, link))
  try:
    os.rename(bn, "%s.todel" % bn)
  except OSError as ose:
    u.warning("unable to process '%s' -- %s" % (link, ose))
    continue
  nf = u.docmdnf("cp %s %s" % (targ, bn))
  if nf != 0:
    u.warning("copy failed, link reverted")
    os.rename("%s.todel" % bn, bn)
    continue
  u.verbose(1, "removing intermediate %s.todel" % bn)
  os.unlink("%s.todel" % bn)
