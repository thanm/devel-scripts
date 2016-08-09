#!/usr/bin/python
"""Summarize data section sizes in an Android load module.

Summarize section size info for specified set of Android load
modules by running "objdump".

"""

from collections import defaultdict
import getopt
import locale
import os
import re
import shlex
import subprocess
import sys
import script_utils as u


# Command line -A was set: read all *.so files from
# $ANDROID_PRODUCT_OUT/system
flag_examine_allshlibs = 0

# Check input files to make sure they are in .../symbols dir
flag_check_in_symbols = 1

# List of input files collected from command line
flag_input_files = []

# Selection for -r arg (either 32 or 64)
flag_restrict_elf = None

# Target or host mode
flag_filemode = "target"

# Setting of $ANDROID_BUILD_TOP
abt = ""

# Setting of $ANDROID_PRODUCT_OUT
apo = ""

# Interesting sections
insections = {
    ".rodata": 0,
    ".text": 0,
    ".data": 0,
    ".bss": 0,
    ".data.rel.ro": 0,
    ".data.rel.ro.local": 0
    }

# Sections for size analysis
sizeinsections = insections

# Abbreviations
abbrevsections = {
    ".data.rel.ro": ".DRR",
    ".data.rel.ro.local": ".DRRL"
    }

# Dictionary of section sizes across all args
allsecsizes = defaultdict(int)


def in_symbols_dir(filename):
  """Make sure input file is part of $ANROID_PRODUCT_OUT/symbols."""

  if flag_filemode == "host" or flag_check_in_symbols == 0:
    return True

  u.verbose(2, "in_symbols_dir(%s)" % filename)
  smatch = re.compile(r"^(\S+)\/symbols\/\S+$")
  sm = smatch.match(filename)
  if sm is None:
    u.verbose(2, "/symbols/ match failed for %s" % filename)
    return False
  pre = sm.group(1)
  u.verbose(2, "pre=%s apo=%s abt=%s" % (pre, apo, abt))
  if pre == apo:
    return True
  fp = "%s/%s" % (abt, pre)
  return fp == apo


def determine_objdump(filename):
  """Figure out what flavor of object dumper we should use."""

  lines = u.docmdlines("file %s" % filename)
  matchers = [(re.compile(r".*ELF.+ARM aarch64"),
               "aarch64-linux-android-objdump"),
              (re.compile(r".*ELF.+ARM"),
               "arm-linux-androideabi-objdump"),
              (re.compile(r".*ELF.+x86\-64"),
               "objdump"),
              (re.compile(r".*ELF.+Intel"),
               "objdump")]
  for l in lines:
    for tup in matchers:
      m = tup[0]
      res = m.match(l)
      if res is None:
        continue
      objdump_cmd = tup[1]
      return objdump_cmd
  u.error("unable to determine objdump flavor to use on %s" % filename)
  return "%unknown%"


def run_objdump_cmd(cargs, filename):
  """Run objdump with specified args, returning list of lines."""

  objdump_cmd = determine_objdump(filename)

  cmd = "%s %s %s" % (objdump_cmd, cargs, filename)
  u.verbose(1, "objdump cmd: %s" % cmd)
  splargs = shlex.split(cmd)
  mypipe = subprocess.Popen(splargs, stdout=subprocess.PIPE)
  encoding = locale.getdefaultlocale()[1]
  pout, perr = mypipe.communicate()
  if mypipe.returncode != 0:
    decoded_err = perr.decode(encoding)
    u.warning(decoded_err)
    u.error("command failed (rc=%d): cmd was %s" % (mypipe.returncode, cmd))
  decoded = pout.decode(encoding)
  return decoded.strip().split("\n")


def skip_this_elf(filename, lines, eflav):
  """Return whether we should skip this elf."""
  matcher = re.compile(r"^\S+:\s+file format elf(\d\d)\-")
  for line in lines:
    if not line:
      continue
    m = matcher.match(line)
    if m:
      dd = int(m.group(1))
      if dd != 32 and dd != 64:
        u.error("internal error: bad elf %s flavor %d "
                "(line %s)" % (filename, dd, line))
      if dd != eflav:
        # Not correct flavor
        return True
      else:
        return False
  u.error("internal error: could not find file format line")


def imagename(f):
  """Return name of file relative to $ANDROID_PRODUCT_OUT."""
  if not flag_examine_allshlibs:
    return basename(f)
  s = "%s/symbols/" % apo
  apolen = len(s)
  return f[apolen:]


def examine_sections(filename):
  """Examine section info for image."""

  objdump_args = "-h -w"
  lines = run_objdump_cmd(objdump_args, filename)

  if flag_restrict_elf and skip_this_elf(filename, lines, flag_restrict_elf):
    u.verbose(1, "skipping file %s, wrong elf flavor" % filename)
    return

  # Pattern we're looking for in the objdump output
  matcher = re.compile(r"^\s+\d+\s+(\S+)\s+(\S+)\s+(\S+)"
                       r"\s+(\S+)\s+(\S+)\s+(\S+)")

  # Run through all of the lines:
  secdict = defaultdict(int)
  for line in lines:
    if not line:
      continue
    # Match
    m = matcher.match(line)
    if m is None:
      # Should not refer to any interesting sections
      tokens = line.split()
      for t in tokens:
        if t in insections:
          u.error("%s: line failed match but contains "
                  "interesting section %s: %s" % (filename, t, line))
      continue

    # match succeeded
    secname = m.group(1)
    secsize = int(m.group(2), base=16)
    secdict[secname] = secsize
    allsecsizes[secname] += secsize

  secoutput(secdict, imagename(filename), 0)


def examine_file(filename):
  """Perform symbol analysis on specified file."""
  if not in_symbols_dir(filename):
    u.warning("%s: does not appear to be in "
              "%s/symbols directory? skipping" % (filename, apo))
    return
  u.verbose(1, "visiting file %s" % filename)
  examine_sections(filename)


def secoutput(secsizes, name, isheader):
  """Output size line or size line header."""
  sys.stdout.write("%-50s " % name)
  sortedsecs = sorted(sizeinsections.keys())
  for ss in sortedsecs:
    szs = ""
    if ss in secsizes:
      szs = str(secsizes[ss])
    else:
      szs = "0"
    if isheader:
      if ss in abbrevsections:
        ss = abbrevsections[ss]
      szs = ss
    sys.stdout.write("%10s " % szs)
  sys.stdout.write("\n")


def collect_allshlibs():
  """Collect names of all shlibs in $ANDROID_PRODUCT_OUT/symbols."""
  cmd = "find %s/symbols/system -name '*.so' -print" % apo
  u.verbose(1, "find cmd: %s" % cmd)
  cargs = shlex.split(cmd)
  mypipe = subprocess.Popen(cargs, stdout=subprocess.PIPE)
  pout, _ = mypipe.communicate()
  if mypipe.returncode != 0:
    u.error("command failed (rc=%d): cmd was %s" % (mypipe.returncode, cmd))
  encoding = locale.getdefaultlocale()[1]
  decoded = pout.decode(encoding)
  lines = decoded.strip().split("\n")
  u.verbose(1, "found a total of %d libs" % len(lines))
  return lines


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options] <files>

    options:
    -A    process all *.so files in $ANDROID_PRODUCT_OUT/system
    -H    image of interest is host and not target
    -d    increase debug msg verbosity level
    -X    skip check to to make sure lib is in symbols dir
    -r {32,64} restrict analysis to just ELF-32 or just ELF-64 files

    """ % os.path.basename(sys.argv[0])
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_examine_allshlibs, flag_check_in_symbols, flag_filemode
  global flag_input_files, flag_restrict_elf, apo, abt

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "dr:AHX")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-A":
      flag_examine_allshlibs = 1
    elif opt == "-H":
      flag_filemode = "host"
    elif opt == "-X":
      flag_check_in_symbols = 0
    elif opt == "-r":
      if arg == "32":
        flag_restrict_elf = 32
      elif arg == "64":
        flag_restrict_elf = 64
      else:
        usage("argument to -r option must be either 32 or 64")

  if not args and flag_examine_allshlibs == 0:
    usage("specify at least one input file or use -A option")

  if args and flag_examine_allshlibs == 1:
    usage("specify either -A or a specific input file")

  flag_input_files = args

  abt = os.getenv("ANDROID_BUILD_TOP")
  if abt is None:
    u.error("ANDROID_BUILD_TOP not set (did you run lunch?)")
  apo = os.getenv("ANDROID_PRODUCT_OUT")
  if apo is None:
    u.error("ANDROID_PRODUCT_OUT not set (did you run lunch?)")

#----------------------------------------------------------------------
# Main portion of script
#

u.setdeflanglocale()
parse_args()

fileargs = flag_input_files
if flag_examine_allshlibs:
  fileargs = collect_allshlibs()

secoutput(insections, "name", 1)

for filearg in sorted(fileargs):
  examine_file(filearg)

secoutput(allsecsizes, "total", 0)
secoutput(insections, "name", 1)
