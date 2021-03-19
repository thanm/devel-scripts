#!/usr/bin/python3
"""Extracts compile command line from ninja build output.

Reads either stdin or a specified input file, then extracts out
clang/g++ compile command line, post-processes it to remove offensive
stuff, then emits into separate shell script. Useful for rerunning
compiler by hand in situations where build fails.

"""

import getopt
import hashlib
import os
import re
import shlex
import sys

import script_utils as u

# Extract single cmd vs all cmds
flag_single = True

# Extract single cmd per srcfile
flag_unique = False

# Input and output file (if not specified, defaults to stdin/stdout)
flag_infile = None
flag_outfile = None

# Drivers we encounter while scanning the build output
drivers = {}
driver_count = 0

# Exclude host compiles
flag_exclude_host = False

# Exclude target compiles
flag_exclude_target = False

# Include only compiles with -target set to this
flag_target = None

# Experimental compile-in-parallel feature
flag_parfactor = 0

# Compile cmd line args to skip. Key is arg, val is skip count.
args_to_skip = {"-o": 1, "-MD": 0, "-MF": 1, "-fdiagnostics-color": 0}


def mktempname(salt, instance):
  """Create /tmp file name for compile output."""
  m = hashlib.md5()
  m.update(salt)
  hd = m.hexdigest()
  return "/tmp/%s.%d.err.txt" % (hd, instance)


def perform_extract(inf, outf):
  """Read inf and extract compile cmd to outf."""
  global driver_count
  regfg = re.compile(r"^.+\s+(prebuilts\/gcc\S+)\s.+$")
  regfc = re.compile(r"^.+\s+(prebuilts\/clang\S+)\s.+$")
  reg1 = re.compile(r"^.+PWD=\S+\s+(prebuilts\/\S+)\s+(.+)\)\s+\&\&\s+\(.+$")
  preamble_emitted = False
  count = 0
  tempfiles = []
  srcfiles_encountered = {}
  while True:
    line = inf.readline()
    if not line:
      break
    u.verbose(2, "line is %s" % line.strip())
    mc = regfc.match(line)
    mg = regfg.match(line)
    if not mc and not mg:
      continue

    # This should pluck out the compiler invocation
    mi = reg1.match(line)
    if not mi:
      # Skip strip, ar, etc
      if (not re.compile(r"^.+\-android.*\-strip .+$").match(line) and
          not re.compile(r"^.+Wl,\-soname.+$").match(line) and
          not re.compile(r"^.+Wl,\-\-build\-id=md5.+$").match(line) and
          not re.compile(r"^.+\-android\-ar .+$").match(line)):
        u.warning("line refers to prebuilt gcc/clang but fails "
                  "pattern match: %s" % line.strip())
      continue
    if not preamble_emitted:
      preamble_emitted = True
      outf.write("#!/bin/sh\n")
    driver = mi.group(1)
    argstring = mi.group(2)
    u.verbose(1, "matched: %s %s" % (driver, argstring))

    driver_var = "DRIVER%d" % driver_count
    if driver in drivers:
      driver_var = drivers[driver]
    else:
      outf.write("%s=%s\n" % (driver_var, driver))
      drivers[driver] = driver_var
      driver_count += 1

    matchhost = re.compile("^.*out\/host\/.+$")
    matchtarget = re.compile("^.*out/target/.+$")

    # Now filter the args. Pick out -MD, -MF, -o, etc so as to leave us
    # with the raw compile cmd that is more manageable.
    exclude = False
    args = []
    skipcount = 0
    raw_args = shlex.split(argstring)
    numraw = len(raw_args)
    incfile = None
    msrc = re.compile(r"^\S+\.[Ccp]+$")
    for idx in range(0, numraw):
      arg = raw_args[idx]
      if flag_exclude_target and matchtarget.match(arg):
        u.verbose(2, "excluding compile (target match on %s)" % arg)
        exclude = True
      if flag_exclude_host and matchhost.match(arg):
        u.verbose(2, "excluding compile (host match on %s)" % arg)
        exclude = True
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
      if arg == "$(cat":
        if incfile:
          u.error("internal error: multiple $cat( clauses")
        incfile = raw_args[idx+1]
        rei = re.compile(r"^(.+)\)$")
        mei = rei.match(incfile)
        if not mei:
          u.error("internal error: malformed $cat clause: arg %s" % incfile)
        incfile = mei.group(1)
        skipcount = 1
        u.verbose(2, "skipping arg: %s (skipcount set to 1)" % arg)
        args.append("$INC")
        continue
      if flag_target and arg == "-target" and raw_args[idx+1] != flag_target:
        u.verbose(2, "excluding compile (target %s not selected)" % raw_args[idx+1])
        exclude = True
      args.append(arg)
    if not exclude and flag_unique:
      srcfile = args[-1]
      u.verbose(1, "srcfile is %s" % srcfile)
      if not msrc.match(srcfile):
        u.warning("suspicious srcfile %s (no regex match)" % srcfile)
      if srcfile in srcfiles_encountered:
        exclude = True
        u.verbose(1, "excluding compile (seen src %s already)" % srcfile)
      srcfiles_encountered[srcfile] = 1
    if exclude:
      continue
    if incfile:
      outf.write("INC=`cat %s`\n" % incfile)
    extra = ""
    if flag_parfactor:
      tempfile = mktempname(line, count)
      tempfiles.append(tempfile)
      extra = "&> %s &" % tempfile
      count = count + 1
    outf.write("${%s} %s $* %s\n" % (driver_var, " ".join(args), extra))
    u.verbose(0, "extracted compile cmd for %s" % raw_args[numraw-1])
    if flag_single:
      return
    if count > flag_parfactor:
      outf.write("wait\n")
      outf.write("cat %s\n" % " ".join(tempfiles))
      outf.write("rm %s\n" % " ".join(tempfiles))
      tempfiles = []
      count = 0
  if count:
    outf.write("wait\ncat")
    for t in tempfiles:
      outf.write(" %s" % t)
    outf.write("\n")





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


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options] < input > output

    options:
    -d    increase debug msg verbosity level
    -i F  read from input file F (presumable captured android build output)
    -o G  write compile script to file G
    -H    exclude host compiles
    -T    exclude target compiles
    -t X  include only clang compiles with -target X
    -a    extract all compile cmds (not just first one found)
    -u    when -a is in effect, extract single compile command for
          a given srcfile
    -j N  emit code to perform N compilations in parallel


    """ % os.path.basename(sys.argv[0]))
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_infile, flag_outfile, flag_single, flag_parfactor
  global flag_exclude_host, flag_exclude_target, flag_target
  global flag_unique

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "HTdaui:o:t:j:")
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
    elif opt == "-u":
      flag_unique = True
    elif opt == "-i":
      flag_infile = arg
    elif opt == "-o":
      flag_outfile = arg
    elif opt == "-t":
      flag_target = arg
    elif opt == "-j":
      flag_parfactor = int(arg)
    elif opt == "-H":
      flag_exclude_host = True
    elif opt == "-T":
      flag_exclude_target = True
  if flag_single:
    flag_parfactor = 0

# Setup
u.setdeflanglocale()
parse_args()
perform()
