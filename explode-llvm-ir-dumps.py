#!/usr/bin/python
"""Explode an LLVM IR dump.

Given a debug dump generated from the -print-debug-all option, split out the
dumps into multiple files, one for each phase/procedure. Example usage:

  clang -c -O3 -mllvm -print-before-all mumble.c 1> err.txt 2>&1
  rm -rf /tmp/dumps ; mkdir /tmp/dumps
  explode-llvm-ir-dumps.py -i err.txt -o /tmp/dumps

Right at the moment (this could change in the future), the output of
-print-before-all includes both function-scope dumps and module-scope
dumps. The expected pattern will be something like

  mod dump 1 pass X
  mod dump 2 pass Y
  func 1 dump for pass A
  func 1 dump for pass B
  func 1 dump for pass C
  func 2 dump for pass A
  func 2 dump for pass B
  func 2 dump for pass C
  mod dump 3 pass Z

Typically what we're interested in doing is tracking a function over time
through the various dumps, so we emit an index ("index.txt") containing a
chronological listing of the dumps that mention a function (the assumption being
that a module dump mentions all functions).

Bugs: does not handle loop dumps.

"""

from collections import defaultdict
import getopt
import os
import re
import sys

import script_utils as u

# Dry run mode
flag_dryrun = False

# Echo commands mode
flag_echo = False

# Input file, output dir
flag_infile = None
flag_outdir = None

# Passes, functions
passes = {}
functions = {}

# Key is dump name (func:pass) and value is counter (how many
# dumps we've seen for this dumpname, since a given pass can
# happen more than once for a given function).
dumps = defaultdict(int)

# Complete listing of dump files in chronological order.
alldumps = []

# Keyed by function, value is a list of indices into the alldumps array.
funcdumps = defaultdict(list)


def docmd(cmd):
  """Execute a command."""
  if flag_echo or flag_dryrun:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmd(cmd)


def dochdir(thedir):
  """Switch to dir."""
  if flag_echo or flag_dryrun:
    sys.stderr.write("cd " + thedir + "\n")
  try:
    os.chdir(thedir)
  except OSError as err:
    u.error("chdir failed: %s" % err)


def do_clean(subdir):
  """Clean this libgo dir."""
  flavs = (".o", "gox", ".a", ".so", ".lo", ".la")
  here = os.getcwd()
  dochdir(subdir)
  if flag_dryrun:
    u.verbose(0, "... cleaning %s" % subdir)
  else:
    cmd = "find . -depth "
    first = True
    for item in flavs:
      if not first:
        cmd += " -o "
      first = False
      cmd += "-name '*%s' -print" % item
    lines = u.docmdlines(cmd)
    lines.reverse()
    debris = lines
    for d in debris:
      if not d:
        continue
      u.verbose(1, "toclean '%s'" % d)
      os.unlink(d)
  dochdir(here)


def sanitize_pass(passname):
  """Sanitize passname to remove embedded spaces, etc."""
  passname = passname.replace(" ", "_")
  passname = passname.replace("(", ".LP")
  passname = passname.replace(")", ".RP")
  passname = passname.replace("/", ".SL")
  passname = passname.replace("'", ".SQ")
  return passname


def emitdump(passname, funcname, lines):
  """Emit single dump for module/pass or fn/pass."""
  tag = funcname
  if not funcname:
    tag = "__module__"
  dump = "%s:%s" % (tag, passname)
  dumpver = dumps[dump]
  dumps[dump] += 1
  dumpname = "%s:%s:%d" % (tag, passname, dumpver)
  ofname = os.path.join(flag_outdir, dumpname)
  try:
    with open(ofname, "w") as wf:
      for line in lines:
        wf.write(line)
  except IOError:
    u.error("open failed for %s" % ofname)
  u.verbose(1, "emitted dump %d of %d "
            "lines to %s" % (dumpver, len(lines), ofname))
  # book-keeping
  dumpidx = len(alldumps)
  alldumps.append(dumpname)
  if funcname:
    funcdumps[funcname].append(dumpidx)
  return dumpname


def process(rf):
  """Read lines from input file."""

  # Note: dumps are emitted lazily, e.g. we read through all of dump K
  # and into dump K+1 before emitting dump K.

  lnum = 0
  dumpre = re.compile(r"^\*\*\* IR Dump Before (\S.+)\s+\*\*\*\s*")
  fnre = re.compile(r"^define\s\S.+\s\@(\S+)\(.+\).+\{\s*$")
  modre = re.compile(r"^target datalayout =.*$")

  # Info on previous dump
  curpass = None
  curfunc = None
  curdumplines = []

  # Whether current dump is module (true) or function (false)
  ismod = False
  # Lines in current dump
  dumplines = []
  passname = None

  while True:
    lnum += 1
    line = rf.readline()
    if not line:
      break
    mmod = modre.match(line)
    if mmod:
      # Emit previous dump (which may have been mod or func)
      if curpass:
        emitdump(curpass, curfunc, curdumplines)
      curfunc = None
      # This is a module dump, not a function dump.
      ismod = True
      u.verbose(1, "line %d: now in module dump "
                "for pass %s" % (lnum, curpass))
    if not ismod:
      mfn = fnre.match(line)
      if mfn:
        # Emit previous dump (which may have been mod or func)
        if curpass:
          emitdump(curpass, curfunc, curdumplines)
        curfunc = mfn.group(1)
        functions[curfunc] = 1
        u.verbose(1, "line %d: now in fn %s" % (lnum, curfunc))
    mdmp = dumpre.match(line)
    if mdmp:
      ismod = False
      curpass = passname
      passname = sanitize_pass(mdmp.group(1))
      u.verbose(1, "line %d: passname is %s" % (lnum, passname))
      curdumplines = dumplines
      dumplines = []
      passes[passname] = 1
    dumplines.append(line)
  # emit final dump
  if curpass:
    emitdump(curpass, curfunc, curdumplines)


def emitstats():
  """Emit stats and index."""
  indname = os.path.join(flag_outdir, "index.txt")
  totaldumps = 0
  for _, v in dumps.iteritems():
    totaldumps += v
  u.verbose(0, "... captured %d total dumps, %d functions, "
            "%d passes" % (totaldumps, len(functions), len(passes)))
  try:
    with open(indname, "w") as wf:
      sfuncs = sorted(functions.keys())
      for f in sfuncs:
        wf.write("\n\nfunction '%s':\n" % f)
        indices = funcdumps[f]
        for idx in indices:
          dumpname = alldumps[idx]
          wf.write("  %s\n" % dumpname)
  except IOError:
    u.error("open failed for %s" % indname)
  u.verbose(0, "... emitted dump catalog to %s" % indname)


def perform():
  """Top level driver routine."""
  try:
    with open(flag_infile, "r") as rf:
      process(rf)
  except IOError:
    u.error("open failed for %s" % flag_infile)
  emitstats()


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options]

    options:
    -d    increase debug msg verbosity level
    -o X  write dumps to dir X
    -D    dryrun mode (echo commands but do not execute)

    """ % me
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_dryrun, flag_echo, flag_outdir, flag_infile

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "deo:i:D")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))
  if args:
    usage("unknown extra args")

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-e":
      flag_echo = True
    elif opt == "-D":
      flag_dryrun = True
    elif opt == "-o":
      flag_outdir = arg
      if not os.path.exists(flag_outdir):
        usage("argument to -o flag '%s' not accessible" % arg)
      if not os.path.isdir(flag_outdir):
        usage("argument to -o flag '%s' not a directory" % arg)
    elif opt == "-i":
      flag_infile = arg
      if not os.path.exists(flag_infile):
        usage("argument to -i flag '%s' not accessible" % arg)
  if not flag_outdir:
    usage("supply out dir path with -o")
  if not flag_infile:
    usage("supply input file path with -i")


parse_args()
u.setdeflanglocale()
perform()
