#!/usr/bin/python
"""Runs clang command to generated bitcode, then runs opt/llc with options.

Given a clang command of the form "clang .... -c mumble.c", this
script runs clang with the appropriate options to generate a
bitcode file, then runs opt and llc on the bitcode file with specific
options.

The motivations here are:

  - make it easier to capture / emit LLVM ir at various stages

  - allow passing of options to opt/llc that are not accepted by
    clang (for example, passing "-debug-only=stack-coloring" to llc)

Usage example 1:

  wrap-clang-bitcode.py -L -debug -- clang++ <options> -c -O2 mumble.cc

  This compiles "mumble.cc" with clang++ to emit LLVM IR, then optimizes
  the result with "opt -O2", and finally passes the result to "llc" with
  the "-debug" flag.

Usage example 2:

  wrap-clang-bitcode.py -P -O -p  -- clang <options> -c -O3 abc.c

  This compiles "abc.c" with clang to emit LLVM IR, then optimizes
  the result with "opt -O3 -p", and finally passes the result to "llc".
  Use of the "-P" flag preserves all bitcode/asm files.

Pathnames for bitcode dumps (when -P is used) are derived from the base
name of the source file plus the producing pass, e.g. for abc.c above you
would see

  abc.clang.bc       bitcode produced by clang
  abc.clang.ll       readable dump of the abc.clang.bc
  abc.opt.bc         bitcode produced by opt
  abc.opt.ll         readable dump of the abc.opt.bc

"""

import getopt
import hashlib
import os
import re
import sys

import script_utils as u

# Echo command before executing
flag_echo = True

# Dry run mode
flag_dryrun = False

# Path to clang, llc, opt, llvm-dis
flag_clangbin = None
flag_llcbin = None
flag_optbin = None
flag_disbin = None

# Keep temp files around
flag_preserve_bitcode = False

# Options to pass to llc, opt, clang
flag_clang_opts = []
flag_llc_opts = []
flag_opt_opts = []

# Hash of command line args
arghash = None

# Base name of input src file (would be "./a/abc" if input is "./a/abc.c")
basename = None

# Args passed to clang that we pass on to opt/llc
passargs = {"-O": 1, "-O0": 1, "-O1": 1, "-O2": 1, "-O3": 1}

# temp files generated
tempfiles = {}


def docmdnf(cmd):
  """Execute a command allowing for failure."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return 0
  return u.docmdnf(cmd)


def emitted_path(producer, ext):
  """Convert bitcode path to src path."""
  em = None
  if flag_preserve_bitcode:
    return "%s.%s.%s" % (basename, producer, ext)
  else:
    em = "/tmp/%s.%s.%s.%s" % (arghash, basename, producer, ext)
    tempfiles[em] = 1
    return em


def disdump(producer):
  """Dump a bitcode file to a .ll file."""
  dumpfile = emitted_path(producer, "ll")
  bcfile = emitted_path(producer, "bc")
  args = ("%s %s -o %s " % (flag_disbin, bcfile, dumpfile))
  rc = docmdnf(args)
  if rc != 0:
    u.verbose(1, "llvm-dis returns %d" % rc)
    return


def locate_binaries(clangcmd):
  """Locate executables of interest."""
  global flag_clangbin, flag_llcbin, flag_optbin, flag_disbin

  # Figure out what to invoke
  flag_clangbin = clangcmd
  reg = re.compile("^.*/.*$")
  m = reg.match(clangcmd)
  bindir = None
  if m:
    bindir = os.path.dirname(clangcmd)
    flag_optbin = os.path.join(bindir, "opt")
    flag_llcbin = os.path.join(bindir, "llc")
    flag_disbin = os.path.join(bindir, "llvm-dis")
  else:
    if not flag_dryrun:
      lines = u.docmdlines("which %s" % clangcmd)
      if not lines:
        u.error("which %s returned empty result" % clangcmd)
      clangbin = lines[0].strip()
      bindir = os.path.dirname(clangbin) + "/"
      u.verbose(1, "clang bindir is %s" % bindir)
    else:
      bindir = ""
    flag_clangbin = "%s%s" % (bindir, clangcmd)
    flag_optbin = "%sopt" % bindir
    flag_llcbin = "%sllc" % bindir
    flag_disbin = "%sllvm-dis" % bindir
  if flag_dryrun:
    return

  # Check for existence and executability
  tocheck = [flag_clangbin, flag_optbin, flag_llcbin, flag_disbin]
  for tc in tocheck:
    if not os.path.exists(tc):
      u.error("can't access binary %s" % tc)
    if not os.access(tc, os.X_OK):
      u.error("no execute permission on binary %s" % tc)


def setup():
  """Sort through args, derive basename."""
  global basename
  # Last arg is expected to be src file
  filepath = flag_clang_opts[-1]
  u.verbose(1, "srcfile path is %s" % filepath)
  if not os.path.exists(filepath):
    u.warning("srcpath %s doesn't exist" % filepath)
  # Derive basename
  basename = None
  reg = re.compile(r"^(\S+)\.(\S+)$")
  m = reg.match(filepath)
  if m:
    ext = m.group(2)
    if ext == "c" or ext == "cpp":
      basename = m.group(1)
  if not basename:
    u.error("expected .c or .cpp input argument (got %s)" % filepath)


def perform():
  """Main driver routine."""
  setup()

  # Emit post-clang bitcode
  clang_bcfile = emitted_path("clang", "bc")
  args = ("%s -emit-llvm -o %s -Xclang -disable-llvm-passes "
          "%s" % (flag_clangbin, clang_bcfile,
                  " ".join(flag_clang_opts)))
  rc = docmdnf(args)
  if rc != 0:
    u.verbose(1, "clang cmd returns %d" % rc)
    return
  disdump("clang")

  # Emit post-opt bitcode
  opt_bcfile = emitted_path("opt", "bc")
  args = ("%s %s %s -o %s " % (flag_optbin, clang_bcfile,
                               " ".join(flag_opt_opts), opt_bcfile))
  rc = docmdnf(args)
  if rc != 0:
    u.verbose(1, "opt cmd returns %d" % rc)
    return
  disdump("opt")

  # Now run llc command
  args = ("%s %s %s" % (flag_llcbin, opt_bcfile,
                        " ".join(flag_llc_opts)))
  rc = docmdnf(args)
  if rc != 0:
    u.verbose(1, "llc cmd returns %d" % rc)
    return

  # Remove temps if we are done
  if not flag_preserve_bitcode:
    for t in tempfiles:
      u.verbose(1, "removing temp file %s" % t)
      os.unlink(t)


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options] -- <clangbinary> <clangoptions>

    options:
    -d    increase debug msg verbosity level
    -e    show commands being invoked
    -D    dry run (echo cmds but do not execute)
    -p    reuse/preserve bitcode files
    -L X  pass option X to llc
    -O Y  pass option Y to opt

    """ % os.path.basename(sys.argv[0])
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_preserve_bitcode, flag_dryrun, flag_echo, arghash

  try:
    optlist, _ = getopt.getopt(sys.argv[1:], "depDL:O:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-e":
      flag_echo = True
    elif opt == "-D":
      flag_dryrun = True
    elif opt == "-L":
      flag_llc_opts.append(arg)
    elif opt == "-O":
      flag_opt_opts.append(arg)
    elif opt == "-p":
      flag_preserve_bitcode = True

  # Walk through command line and locate --
  nargs = len(sys.argv)
  clangbin = None
  foundc = False
  for ii in range(0, nargs):
    arg = sys.argv[ii]
    if arg == "--":
      clangbin = sys.argv[ii+1]
      for clarg in sys.argv[ii+2:]:
        flag_clang_opts.append(clarg)
        if clarg == "-c":
          foundc = True
        if clarg in passargs:
          flag_opt_opts.append(clarg)
          flag_llc_opts.append(clarg)
  if not clangbin:
    usage("malformed command line, no -- arg or no clang mentioned")
  if not foundc:
    u.warning("adding -c to clang invocation")
    flag_clang_opts.append("-c")

  locate_binaries(clangbin)

  u.verbose(1, "clangbin: %s" % flag_clangbin)
  u.verbose(1, "llc options: %s" % " ".join(flag_llc_opts))
  u.verbose(1, "opt options: %s" % " ".join(flag_opt_opts))
  u.verbose(1, "clang args: %s" % " ".join(flag_clang_opts))

  # compute arghash for later use
  m = hashlib.md5()
  for a in sys.argv:
    m.update(a)
  arghash = m.hexdigest()


# Setup
u.setdeflanglocale()
parse_args()
perform()
