#!/usr/bin/python
"""Extracts compile commands from go build output.

Reads either stdin or a specified input file, then extracts out
go compiler invocations, post-processes them to strip build directory
artifacts, and emits a separate shell script containing the invocations.
Useful for doing compiler reruns and re-invocations under the debugger.

"""

import getopt
import hashlib
import os
import re
import shlex
import subprocess
import sys


import script_utils as u

# Extract single cmd vs all cmds
flag_single = True

# Input and output file (if not specified, defaults to stdin/stdout)
flag_infile = None
flag_outfile = None

# Set up for gccgo debugging
flag_gccgo_gdb = False

# Captures first gccgo compilation line
gccgo_invocation = None
gccgo_location = None

# Drivers we encounter while scanning the build output
drivers = {}
driver_count = 0

# Experimental compile-in-parallel feature
flag_parfactor = 0

# Compile cmd line args to skip. Key is arg, val is skip count.
args_to_skip = {"-o": 1}

pfcount = 0
pftempfiles = []


def mktempname(salt, instance):
  """Create /tmp file name for compile output."""
  m = hashlib.md5()
  m.update(salt)
  hd = m.hexdigest()
  return "/tmp/%s.%d.err.txt" % (hd, instance)


def extract_line(outf, driver, driver_var, argstring, curdir):
  """Post-process a line."""
  global pfcount, gccgo_invocation, gccgo_location
  # Now filter the args.
  args = []
  skipcount = 0
  regsrc = re.compile(r"^(\S+)\.go$")
  raw_args = shlex.split(argstring)
  numraw = len(raw_args)
  for idx in range(0, numraw):
    arg = raw_args[idx]
    if skipcount:
      u.verbose(2, "skipping arg: %s" % arg)
      skipcount -= 1
      continue
    if arg in args_to_skip:
      sk = args_to_skip[arg]
      if idx + sk >= numraw:
        u.error("at argument %s (pos %d): unable to skip"
                "ahead %d, not enough args (line: "
                "%s" % (arg, idx, sk, " ".join(raw_args)))
      skipcount = sk
      u.verbose(2, "skipping arg: %s (skipcount set to %d)" % (arg, sk))
      continue
    args.append(arg)

  srcfile = args[-1]
  u.verbose(1, "srcfile is %s" % srcfile)
  if not regsrc.match(srcfile):
    u.warning("suspicious srcfile %s (no regex match)" % srcfile)

  extra = ""
  if flag_parfactor:
    line = driver . argstring
    tempfile = mktempname(line, pfcount)
    pftempfiles.append(tempfile)
    extra = "&> %s &" % tempfile
    pfcount += 1
  outf.write("${%s} %s $* %s\n" % (driver_var, " ".join(args), extra))
  u.verbose(0, "extracted compile cmd for %s" % raw_args[numraw-1])
  if flag_gccgo_gdb:
    gccgo_invocation = []
    gccgo_invocation.append(driver)
    gccgo_invocation.extend(args)
    gccgo_location = curdir
  if flag_single:
    return -1
  return 1


def perform_extract(inf, outf):
  """Read inf and extract compile cmd to outf."""
  global driver_count, pfcount, pftempfiles

  reggcg = re.compile(r"^(\S+/bin/gccgo)\s+(.+)$")
  reggc = re.compile(r"^(\S+/compile)\s+(.+)$")
  regcd = re.compile(r"^cd (\S+)\s*$")
  preamble_emitted = False
  pfcount = 0
  pftempfiles = []
  cdir = "."
  while True:
    line = inf.readline()
    if not line:
      break
    u.verbose(2, "line is %s" % line.strip())
    mcd = regcd.match(line)
    if mcd:
      cdir = mcd.group(1)
      continue
    mgc = reggc.match(line)
    mgcg = reggcg.match(line)
    if not mgc and not mgcg:
      continue
    if mgc:
      driver = mgc.group(1)
      argstring = mgc.group(2)
    else:
      driver = mgcg.group(1)
      argstring = mgcg.group(2)

    if not preamble_emitted:
      preamble_emitted = True
      outf.write("#!/bin/sh\n")
      outf.write("WORK=`pwd`\n")
    u.verbose(1, "matched: %s %s" % (driver, argstring))

    driver_var = "DRIVER%d" % driver_count
    if driver in drivers:
      driver_var = drivers[driver]
    else:
      outf.write("%s=%s\n" % (driver_var, driver))
      drivers[driver] = driver_var
      driver_count += 1
    if extract_line(outf, driver, driver_var, argstring, cdir) < 0:
      break
    if pfcount > flag_parfactor:
      outf.write("wait\n")
      outf.write("cat %s\n" % " ".join(pftempfiles))
      outf.write("rm %s\n" % " ".join(pftempfiles))
      pftempfiles = []
      pfcount = 0

  if pfcount:
    outf.write("wait\ncat")
    for t in pftempfiles:
      outf.write(" %s" % t)
    outf.write("\n")


def setup_gccgo_gdb():
  """Set up for gccgo debugging."""
  outfile = ".gccgo.err.txt"
  here = os.getcwd()
  if here != gccgo_location:
    u.warning("gccgo compile takes place in %s, "
              "not here (%s)" % (gccgo_location, here))
  objfile = "%s/.gccgo.tmp.o" % here
  os.chdir(gccgo_location)
  driver = gccgo_invocation[0]
  args = gccgo_invocation[1:]
  for idx in range(0, len(args)):
    if args[idx] == "$WORK":
      args[idx] = here
  cmd = ("%s -v -o %s %s" % (driver, objfile, " ".join(args)))
  u.verbose(1, "executing gdb setup cmd: %s" % cmd)
  u.docmderrout(cmd, outfile, True)
  os.chdir(here)
  try:
    inf = open(outfile, "rb")
  except IOError as e:
    u.error("internal error: unable to consume tmp "
            "file %s? error %s" % (outfile, e.strerror))
  lines = inf.readlines()
  inf.close()
  reg1 = re.compile(r"^\s*(\S+/go1)\s+(\S.+)$")
  found = False
  for line in lines:
    m = reg1.match(line)
    if m:
      go1exe = m.group(1)
      u.verbose(1, "go1 driver is %s" % go1exe)
      go1args = m.group(2)
      u.verbose(1, "go1 args: %s" % go1args)
      found = True
      # Create symlink
      if not os.path.exists("go1"):
        u.verbose(0, "symlinking to %s" % go1exe)
        os.symlink(go1exe, "go1")
      # Dump args
      u.verbose(0, "writing args to .gdbinit")
      try:
        outf = open(".gdbinit", "wb")
      except IOError as e:
        u.error("unable to open ./.gdbinit: "
                "%s" % (flag_outfile, e.strerror))
      outf.write("# gud-gdb --fullname ./go1\n")
      outf.write("set args %s" % go1args)
      outf.close()
      u.verbose(0, "starting emacs")
      subprocess.Popen(["emacs", ".gdbinit"])



def perform():
  """Main driver routine."""
  inf = sys.stdin
  outf = sys.stdout
  if flag_infile:
    try:
      inf = open(flag_infile, "rb")
    except IOError as e:
      u.error("unable to open input file %s: "
              "%s" % (flag_infile, e.strerror))
  if flag_outfile:
    try:
      outf = open(flag_outfile, "wb")
    except IOError as e:
      u.error("unable to open output file %s: "
              "%s" % (flag_outfile, e.strerror))
  perform_extract(inf, outf)
  if flag_infile:
    inf.close()
  if flag_outfile:
    outf.close()
  if flag_gccgo_gdb:
    setup_gccgo_gdb()


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options] < input > output

    options:
    -d    increase debug msg verbosity level
    -i F  read from input file F (presumably captured 'go build' output)
    -o G  write compile script to file G
    -a    extract all compile cmds (not just first one found)
    -j N  emit code to perform N compilations in parallel
    -G    set up for gccgo debugging; this invokes the compile script
          with -v and then parses the output to collect gccgo/go1 args

    """ % os.path.basename(sys.argv[0])
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_infile, flag_outfile, flag_single, flag_parfactor
  global flag_gccgo_gdb

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "dai:o:j:G")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  if args:
    usage("extra unknown arguments")
  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-a":
      flag_single = False
    elif opt == "-G":
      flag_gccgo_gdb = True
    elif opt == "-i":
      flag_infile = arg
    elif opt == "-o":
      flag_outfile = arg
    elif opt == "-j":
      flag_parfactor = int(arg)
  if flag_single:
    flag_parfactor = 0

# Setup
u.setdeflanglocale()
parse_args()
perform()
