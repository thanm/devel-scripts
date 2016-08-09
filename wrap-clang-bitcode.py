#!/usr/bin/python
"""Runs clang command to generated bitcode, then runs llc with options.

Given a clang command of the form "clang .... -c mumble.c", this
script runs clang with the appropriate options to generate a
bitcode file, then runs llc on the bitcode file with specific options.

The main motivation here is that there are llc options that (apparently)
are impossible to pass to the back end. Example: -debug-only=stack-coloring.

Example usage:

 wrap-clang-bitcode.py -x -debug -- /bin/clang++ <options> -c mumble.cc

Note that "llc" is drawn from the same location as the clang binary.

"""

import getopt
import hashlib
import os
import subprocess
import sys

import script_utils as u

flag_clangbin = None
flag_llcbin = None
flag_preserve_bitcode = False
flag_clang_args = []
flag_llc_options = []


def bitcode_path(args):
  """Convert bitcode path to src path."""
  m = hashlib.md5()
  for a in args:
    m.update(a)
  hd = m.hexdigest()
  return "/tmp/%s.bco" % hd


def perform():
  """Main driver routine."""
  # Last arg is expected to be src file
  filepath = flag_clang_args[-1]
  u.verbose(1, "srcfile path is %s" % filepath)
  if not os.path.exists(filepath):
    u.warning("srcpath %s doesn't exist" % filepath)
  # Emit bitcode
  bcfile = bitcode_path(flag_clang_args)
  if not flag_preserve_bitcode or not os.path.exists(bcfile):
    args = flag_clang_args
    args = [flag_clangbin, "-emit-llvm", "-o", bcfile] + flag_clang_args
    u.verbose(1, "bc emit clang cmd is %s" % " ".join(args))
    rc = subprocess.call(args)
    u.verbose(1, "clang cmd returns %d" % rc)
  # Now run llc command
  args = [flag_llcbin] + flag_llc_options + [bcfile]
  u.verbose(1, "llc cmd is %s" % " ".join(args))
  rc = subprocess.call(args)
  u.verbose(1, "llc cmd returns %d" % rc)
  if not flag_preserve_bitcode:
    os.unlink(bcfile)


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options] -- <clangbinary> <clangoptions>

    options:
    -d    increase debug msg verbosity level
    -p    reuse/preserve bitcode files
    -x O  pass option O to llc

    """ % os.path.basename(sys.argv[0])
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_clangbin, flag_llc_options, flag_clang_args
  global flag_llcbin, flag_preserve_bitcode

  try:
    optlist, _ = getopt.getopt(sys.argv[1:], "dpx:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-x":
      flag_llc_options.append(arg)
    elif opt == "-p":
      flag_preserve_bitcode = True

  # Walk through command line and locate --
  nargs = len(sys.argv)
  for ii in range(0, nargs):
    arg = sys.argv[ii]
    if arg == "--":
      flag_clangbin = sys.argv[ii+1]
      if not os.path.exists(flag_clangbin):
        usage("clang binary %s doesn't exist" % flag_clangbin)
      flag_clang_args = sys.argv[ii+2:]
  if not flag_clangbin:
    usage("malformed command line, no -- arg")
  u.verbose(1, "clangbin: %s" % flag_clangbin)
  u.verbose(1, "llc options: %s" % " ".join(flag_llc_options))
  u.verbose(1, "clang args: %s" % " ".join(flag_clang_args))
  bindir = os.path.dirname(flag_clangbin)
  flag_llcbin = os.path.join(bindir, "llc")
  if not os.path.exists(flag_llcbin):
    usage("unable to locate llc binary %s" % flag_llcbin)


# Setup
u.setdeflanglocale()
parse_args()
perform()
