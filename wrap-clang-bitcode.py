#!/usr/bin/python3
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

# Paths to clang, llc, opt, llvm-dis
toolpaths = {"clang":"/unknownpath", "llc":"/unknownpath", "opt":"/unknownpath", "llvm-dis":"/unknownpath"}

# Keep temp files around
flag_preserve_bitcode = False

# Generate 'opt' bitcode by manual 'opt' invocation.
flag_explicitly_invoke_opt = False

# Tag result files.
flag_ptag = None

# Options to pass to llc, opt, clang
flag_clang_opts = []
flag_llc_opts = []
flag_opt_opts = []

# If set, pass -O options to llc and opt
flag_pass_olevel = False

# Hash of command line args
arghash = None

# Base name of input src file (would be "./a/abc" if input is "./a/abc.c")
basename = None

# Args passed to clang that we pass on to opt/llc if -T specified. These are
# expressed as regex's.
passargs = {r"^\-O$": 1,
            r"^\-O\d$": 1}

# Args that need to be rewritten/translated.
transargs = {r"^\-march=(\S+)$": "-mcpu=%s"}

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
  b = basename
  if flag_ptag:
    b = "%s.%s" % (basename, flag_ptag)
  if flag_preserve_bitcode:
    return "%s.%s.%s" % (b, producer, ext)
  else:
    em = "/tmp/%s.%s.%s.%s" % (arghash, basename, producer, ext)
    tempfiles[em] = 1
    return em


def disdump(producer):
  """Dump a bitcode file to a .ll file."""
  dumpfile = emitted_path(producer, "ll")
  bcfile = emitted_path(producer, "bc")
  args = ("%s %s -o %s " % (toolpaths["llvm-dis"], bcfile, dumpfile))
  rc = docmdnf(args)
  if rc != 0:
    u.verbose(1, "llvm-dis returns %d" % rc)
    return


def locate_binaries(clangcmd):
  """Locate executables of interest."""
  global toolpaths

  # Figure out what to invoke
  u.verbose(1, "clangcmd is %s" % clangcmd)
  toolpaths["clang"] = clangcmd
  reg = re.compile("(^.*)/(.*)$")
  m = reg.match(clangcmd)
  bindir = None
  clcmd = None
  if m:
    bindir = m.group(1)
    clcmd = m.group(2)
  else:
    if not flag_dryrun:
      lines = u.docmdlines("which %s" % clangcmd)
      if not lines:
        u.error("which %s returned empty result" % clangcmd)
      clangbin = lines[0].strip()
      bindir = os.path.dirname(clangbin) + "/"
      clcmd = os.path.basename(clangbin)
      u.verbose(1, "clang bindir is %s" % bindir)
    else:
      bindir = ""
  toolpaths["clang"] = os.path.join(bindir, clcmd)
  toolpaths["opt"] = os.path.join(bindir, "opt")
  toolpaths["llc"] = os.path.join(bindir, "llc")
  toolpaths["llvm-dis"] = os.path.join(bindir, "llvm-dis")

  if flag_dryrun:
    return

  # If clang is versioned, then version llvm-dis
  reg2 = re.compile("^.+(\-\d\.\d)$")
  m2 = reg2.match(clangcmd)
  if m2:
    toolpaths["llvm-dis"] = os.path.join(bindir, "llvm-dis%s" % m2.group(1))

  # Check for existence and executability
  tocheck = ["clang", "opt", "llc", "llvm-dis"]
  for tc in tocheck:
    path = toolpaths[tc]
    if not os.path.exists(path):
      u.warning("can't access binary %s at path %s" % (tc, path))
    if not os.access(path, os.X_OK):
      u.warning("no execute permission on binary %s" % path)


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
    if ext == "c" or ext == "cpp" or ext == "cc":
      basename = m.group(1)
  if not basename:
    u.error("expected {.c,.cc,.cpp} input argument (got %s)" % filepath)


def perform():
  """Main driver routine."""
  setup()

  # Emit post-clang bitcode
  clang_bcfile = emitted_path("clang", "bc")
  args = ("%s -emit-llvm -o %s -Xclang -disable-llvm-passes "
          "%s" % (toolpaths["clang"], clang_bcfile,
                  " ".join(flag_clang_opts)))
  rc = docmdnf(args)
  if rc != 0:
    u.verbose(1, "clang cmd returns %d" % rc)
    return
  disdump("clang")

  # Emit post-opt bitcode
  opt_bcfile = emitted_path("opt", "bc")
  if flag_explicitly_invoke_opt:
    if os.path.exists(toolpaths["opt"]):
      args = ("%s %s %s -o %s " % (toolpaths["opt"], clang_bcfile,
                                 " ".join(flag_opt_opts), opt_bcfile))
      rc = docmdnf(args)
      if rc != 0:
        u.verbose(1, "opt cmd returns %d" % rc)
        return
      disdump("opt")
    else:
      u.verbose(0, "opt run stubbed out (unable to "
                "access/run %s" % toolpaths["opt"])
  else:
    args = ("%s -emit-llvm -o %s %s" % (toolpaths["clang"], opt_bcfile,
                                        " ".join(flag_clang_opts)))
    rc = docmdnf(args)
    if rc != 0:
      u.verbose(1, "clang cmd returns %d" % rc)
      return
    disdump("opt")

  # Now run llc command
  if os.path.exists(toolpaths["llc"]):
    args = ("%s %s %s" % (toolpaths["llc"], opt_bcfile,
                        " ".join(flag_llc_opts)))
    rc = docmdnf(args)
    if rc != 0:
      u.verbose(1, "llc cmd returns %d" % rc)
      return
  else:
    u.verbose(0, "llc run stubbed out (unable to "
              "access/run %s" % toolpaths["llc"])


  # Remove temps if we are done
  if not flag_preserve_bitcode:
    for t in tempfiles:
      u.verbose(1, "removing temp file %s" % t)
      os.unlink(t)


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options] -- <clangbinary> <clangoptions>

    options:
    -d    increase debug msg verbosity level
    -e    show commands being invoked
    -D    dry run (echo cmds but do not execute)
    -p    reuse/preserve bitcode files
    -x    generate post-opt bitcode by explicitly invoking
          'opt' (usually not a good idea due to options setup)
    -P T  tag preserved files with tag 'T'
    -L X  pass option X to llc
    -O Y  pass option Y to opt

    """ % os.path.basename(sys.argv[0]))
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_preserve_bitcode, flag_dryrun, flag_echo, arghash
  global flag_ptag, flag_pass_olevel, flag_explicitly_invoke_opt

  try:
    optlist, _ = getopt.getopt(sys.argv[1:], "depxDTL:O:P:")
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
    elif opt == "-T":
      flag_pass_olevel = True
    elif opt == "-L":
      flag_llc_opts.append(arg)
    elif opt == "-O":
      flag_opt_opts.append(arg)
    elif opt == "-P":
      flag_ptag = arg
    elif opt == "-p":
      flag_preserve_bitcode = True
    elif opt == "-x":
      flag_explicitly_invoke_opt = True

  # Walk through command line and locate --
  nargs = len(sys.argv)
  clangbin = None
  foundc = False
  for ii in range(0, nargs):
    arg = sys.argv[ii]
    if arg == "--":
      clangbin = sys.argv[ii+1]
      skipnext = False
      for clarg in sys.argv[ii+2:]:
        if skipnext:
          skipnext = False
          continue
        if clarg == "-o" or clarg == "-MT" or clarg == "-MF":
          skipnext = True
          continue
        if clarg == "-MD":
          continue
        flag_clang_opts.append(clarg)
        if clarg == "-c":
          foundc = True
        translated = False
        for rex, tr in transargs.iteritems():
          u.verbose(3, "=-= tmatching clarg %s against %s" % (clarg, rex))
          r = re.compile(rex)
          m = r.match(clarg)
          if m:
            transarg = tr % m.group(1)
            flag_opt_opts.append(transarg)
            flag_llc_opts.append(transarg)
            u.verbose(3, "=-= => translated %s to %s" % (clarg, transarg))
            translated = True
            break
        if translated:
          continue
        if flag_pass_olevel:
          for rex in passargs:
            u.verbose(3, "=-= matching clarg %s against %s" % (clarg, rex))
            r = re.compile(rex)
            m = r.match(clarg)
            if m:
              flag_opt_opts.append(clarg)
              flag_llc_opts.append(clarg)
              u.verbose(3, "=-= => matched")
              break
  if not clangbin:
    usage("malformed command line, no -- arg or no clang mentioned")
  if not foundc:
    u.warning("adding -c to clang invocation")
    flag_clang_opts.append("-c")

  locate_binaries(clangbin)

  u.verbose(1, "clangbin: %s" % toolpaths["clang"])
  u.verbose(1, "llvm-dis: %s" % toolpaths["llvm-dis"])
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
