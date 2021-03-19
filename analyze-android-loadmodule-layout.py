#!/usr/bin/python3
"""Script to analyze layout of text/data objects in an Android load module.

Runs objdump to gather info on the symbols defined in one or more
executables or shared libraries, then tries to detect possible problems
with text/data layout (primarily padding).

"""

from collections import defaultdict
import getopt
import locale
from operator import itemgetter
import os
import re
import shlex
import subprocess
import sys
import script_utils as u


# Show symbols during layout analysis
flag_show_symbols = 0

# Command line -A was set: read all ELF files from
# $ANDROID_PRODUCT_OUT/system
flag_examine_all_loadmodules = 0

# Complain if input files are not in .../symbols directory
flag_check_in_symbols = 1

# Dump summary information about symbol alignment. WARNING: this is
# post-link alignment -- if we find a symbol that is aligned by 4,
# about all we know is that the original symbol had an alignment
# requirements of 4 or less.
flag_dump_sym_alignment = 0

# Target or host mode
flag_filemode = "target"

# Report duplicates (symbols with same name, size, section) if set
flag_report_duplicates = 0

# Report top symbols by size if non-zero
flag_report_topsize = 0

# List of input files collected from command line
flag_input_files = []

# Selection for -r arg (either 32 or 64)
flag_restrict_elf = None

# Objdump cmd, determined on the fly
objdump_cmd = None

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

# In these sections we won't warn about duplicate symbols
nodupsections = {
    ".rodata": 0,
    ".text": 0
    }

# Dictionary of section sizes across all args
allsecsizes = defaultdict(int)

# Total padding in each section
totpaddingbysection = defaultdict(int)

# Total bytes wasted by duplication per section
totdupbytesbysection = defaultdict(int)

# Global alignment histogram for functions
totfuncalign = {}

# Key is section name, value is dict mapping symbol to size
topsym_secdict = defaultdict(lambda: defaultdict(int))


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
  global objdump_cmd

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
      return
  u.error("unable to determine objdump flavor to use on %s" % filename)


def run_objdump_cmd(cargs, filename):
  """Run objdump with specified args, returning list of lines."""

  if not objdump_cmd:
    determine_objdump(filename)

  cmd = "%s %s %s" % (objdump_cmd, cargs, filename)
  u.verbose(2, "objdump cmd: %s" % cmd)
  splargs = shlex.split(cmd)
  mypipe = subprocess.Popen(splargs, stdout=subprocess.PIPE)
  pout, _ = mypipe.communicate()
  if mypipe.returncode != 0:
    u.error("command failed (rc=%d): cmd was %s" % (mypipe.returncode, cmd))
  encoding = locale.getdefaultlocale()[1]
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


def examine_sections(filename):
  """Examine section info for image."""

  # Dict to return
  secsizes = {}

  objdump_args = "-h -w"
  lines = run_objdump_cmd(objdump_args, filename)
  if flag_restrict_elf and skip_this_elf(filename, lines, flag_restrict_elf):
    u.verbose(1, "skipping file %s, wrong elf flavor" % filename)
    return secsizes

  u.verbose(2, "examining objdump output for %s" % filename)

    # Pattern we're looking for in the objdump output
  matcher = re.compile(r"^\s+\d+\s+(\S+)\s+(\S+)"
                       r"\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)")

  # Run through all of the lines:
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
    u.verbose(3, "section %s has size %d" % (secname, secsize))
    secsizes[secname] = secsize

  return secsizes


def examine_symbols(filename, secsizes):
  """Examine symbols for load module."""

  # Dict of dicts -- top level dict is keyed by
  # section name, value for section is dict of syms
  # keyed by offset. Value for second-level dict is pair
  # containing (size, name)
  secdict = defaultdict(lambda: defaultdict(int))

  # Dict of dicts -- top level dict is keyed by
  # section name, value for section is dict of syms
  # keyed by "name:size". Value for second-level dict is
  # count of instances
  dupdict = defaultdict(lambda: defaultdict(str))

  objdump_args = "-w -t"
  lines = run_objdump_cmd(objdump_args, filename)
  if flag_restrict_elf and skip_this_elf(filename, lines, flag_restrict_elf):
    return

  # Pattern we're looking for in the objdump output
  matcher = re.compile(r"^(\S+)\s+(\S+)\s+(\S*)\s+(\.\S+)\s+(\S+)\s+(\S.*)\s*$")

  # Run through all of the lines:
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
    offset = int(m.group(1), base=16)
    symscope = m.group(2)
    symflag = m.group(3)
    secname = m.group(4)
    size = int(m.group(5), base=16)
    symname = m.group(6)

    u.verbose(2, "matched o=%s sc=%s fl=%s sec=%s sz=%s nam=%s" %
              (offset, symscope, symflag, secname, size, symname))

    # Ignore size zero symbols
    if size == 0:
      continue

    # Symbol should not be there already for data sections
    discard = 0
    if (secname in secdict and secname in insections and
        secname not in nodupsections):
      symdict = secdict[secname]
      if offset in symdict:
        p = symdict[offset]
        if p[0] != size:
          u.error("%s: collision on offset %d in section %s: "
                  "line is %s" % (filename, offset, secname, line))
        else:
          discard = 1
    if discard:
      continue

    secdict[secname][offset] = (size, symname)

    # For "top N" size reporting
    if flag_report_topsize:
      record_topsize(secname, size, symname)

    # For duplicate reporting
    if flag_report_duplicates:
      stag = "%s:%d" % (symname, size)
      if stag in dupdict[secname]:
        dupdict[secname][stag] += 1
      else:
        dupdict[secname][stag] = 1

  layout_analysis(secdict, dupdict, filename, secsizes)


def file_is_stripped(secsizes):
  """Look for a .debug_info section to see if file is stripped."""
  if ".debug_info" not in secsizes:
    return True
  return False


def examinefile(filename):
  """Perform symbol analysis on specified file."""
  if not in_symbols_dir(filename):
    u.warning("%s: does not appear to be in "
              "%s/symbols directory? skipping" % (filename, apo))
    return
  secsizes = examine_sections(filename)
  if not secsizes:
    u.verbose(1, "skipping file %s, no contents" % filename)
    return
  if file_is_stripped(secsizes):
    u.verbose(1, "skipping file %s, already stripped" % filename)
    return
  for secname, secsize in secsizes.items():
    allsecsizes[secname] += secsize
  examine_symbols(filename, secsizes)


def collect_alignment(adict, off):
  """Collect alignment histogram."""
  algn = 1
  for ii in range(0, 5):
    mask = 1 << ii
    if off & mask:
      break
    algn *= 2
  if algn in adict:
    adict[algn] += 1
  else:
    adict[algn] = 1
  return algn


def record_topsize(secname, size, symname):
  """Record top N symbols by size."""
  u.verbose(2, "updating top symbol size for "
            "%s name=%s size=%d" % (secname, symname, size))
  secdict = topsym_secdict[secname]
  nentries = len(secdict)
  if nentries < flag_report_topsize:
    secdict[symname] = size
    return
  minsym = None
  minsize = None
  for sm, sz in secdict.items():
    if not minsize or sz < minsize:
      minsize = sz
      minsym = sm
  u.verbose(3, "evicting minsym %s at %d" % (minsym, minsize))
  secdict.pop(minsym, None)
  secdict[symname] = size


def layout_analysis(secdict, dupdict, filename, secsizes):
  """Analyze symbol layout in file."""

  for sec, symdict in secdict.items():

    if sec not in insections:
      continue

    # Produce a sorted list by offset
    sorted_offsets = sorted(symdict.keys())

    # Preamble
    print("")
    print("file: %s section: %s" % (filename, sec))

    # Info on previously processed symbol
    prev_sym_off = -1
    prev_sym_size = -1

    # Maps alignment to number of symbols
    alignments = {}

    # Total padding
    total_padding = 0

    # Symbol size total -- may be different from section size
    total_size = 0

    # Walk through in sorted order
    for off in sorted_offsets:
      algn = collect_alignment(alignments, off)
      tup = symdict[off]
      symsize = tup[0]
      symname = tup[1]
      total_size += symsize
      if prev_sym_off != -1:
        pstart = prev_sym_off + prev_sym_size
        # Detect overlapping symbols -- this happens in libc.so. If we
        # encounter it, then don't try to compute padding for this
        # symbol.
        if pstart > off:
          if flag_show_symbols == 1:
            overlap = pstart = off
            print("   overlap of %d bytes" % overlap)
        else:
          padding = off - pstart
          if padding < 0:
            u.error("internal error: negative padding amount found "
                    "(sym=%s off=0x%x sec=%s poff=0x%x psymsize=%d" %
                    (symname, off, sec, prev_sym_off, prev_sym_size))
          if padding:
            if padding < 8:
              # assume any padding with size >= 8 bytes is a static function
              total_padding += padding
              if flag_show_symbols == 1:
                print(" * 0x%x padding %d bytes" % (pstart, padding))
            else:
              if flag_show_symbols == 1:
                print(" * 0x%x unknown %d bytes" % (pstart, padding))
      if flag_show_symbols == 1:
        algn_str = ""
        if flag_dump_sym_alignment:
          algn_str = "A=%d " % algn
        print("   0x%x S=%d %s%s" % (off, symsize, algn_str, symname))
      prev_sym_size = symsize
      prev_sym_off = off

    if flag_dump_sym_alignment:
      print(" symbol alignment histogram:")
      for algn, count in alignments.items():
        print("  aligned to %d bytes: %d symbols" % (algn, count))
        if sec == ".text":
          if algn in totfuncalign:
            totfuncalign[algn] += count
          else:
            totfuncalign[algn] = count

    stot = secsizes[sec]
    frac = (total_size*1.0 / stot*1.0) * 100.0
    print((" total symbol size is %d (%2.1f%% of "
           "total %s)" % (total_size, frac, secsizes[sec])))

    # For sections such as .text and .data, there are few anonymous
    # locations -- most every bit of storage corresponds to some
    # specific named symbol. The same is not true for .rodata, where
    # you have sizeable chunks of storage that have no name.
    # if sec == ".rodata":
    #      total_padding = 0

    if total_padding:
      totpaddingbysection[sec] += total_padding
      stot = secsizes[sec]
      frac = (total_padding*1.0 / stot*1.0) * 100.0
      print((" padding for %s: %d bytes out of %d total (%2.1f%%)" %
             (sec, total_padding, stot, frac)))

    if flag_report_duplicates:
      report_duplicates(dupdict, sec, secsizes)


def report_duplicates(dupdict, sec, secsizes):
  """Report on duplicate symbols in a section."""
  tagdict = dupdict[sec]

  # Collect duplicates
  rawtups = []
  for tag, count in tagdict.items():
    if count < 2:
      continue
    words = tag.split(":")
    sz = int(words[1])
    tup = (words[0], sz, count, sz*count)
    rawtups.append(tup)

  if not rawtups:
    return

  # Report on duplicates in order of wasteage
  total_dupsize = 0
  stups = sorted(rawtups, key=itemgetter(3, 2, 1, 0))
  for tup in stups:
    name = tup[0]
    sz = tup[1]
    count = tup[2]
    total_dupsize += (count - 1) * sz
    if flag_show_symbols:
      print(" dup symbol %s size %d: %d instances" % (name, sz, count))

  if total_dupsize:
    totdupbytesbysection[sec] += total_dupsize

  # Summarize waste relative to total section size
  stot = secsizes[sec]
  frac = (total_dupsize*1.0 / stot*1.0) * 100.0
  print((" estimated bytes wasted from duplication: "
         "%d (%2.1f%% of total %s)" % (total_dupsize, frac, stot)))


def summarize_dsec(secdict, filename):
  """Summarize contents of interesting sections."""

  if u.verbosity_level() > 2:
    print("Dump of all interesting sections for %s" % filename)
    for sec, symdict in secdict.items():
      if sec not in insections:
        continue
      print("Section: %s" % sec)
      for off, pair in symdict.items():
        sz = pair[0]
        sname = pair[1]
        print("  off %s siz %s name %s" % (off, sz, sname))

  sectotals = {}
  for sec, symdict in secdict.items():
    sectotal = 0
    if sec not in insections:
      continue
    for off, pair in symdict.items():
      sz = pair[0]
      sectotal += sz
      sname = pair[1]
    sectotals[sec] = sectotal


def collect_all_loadmodules():
  """Collect names of all loadmodules in $ANDROID_PRODUCT_OUT/symbols/system."""
  cmd = "find %s/symbols/system -type f -print" % apo
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
  return sorted(lines)


def layout_summary():
  """Print summary information on layout."""
  print("\nTotal padding by section:")
  for sec, pad in totpaddingbysection.items():
    stot = allsecsizes[sec]
    frac = (pad*1.0 / stot*1.0) * 100.0
    print(" %s %d (%2.1f%% of total %d)" % (sec, pad, frac, stot))

  if flag_report_duplicates:
    print("\nTotal bytes (est) wasted from duplication by section:")
    for sec, dup in totdupbytesbysection.items():
      stot = allsecsizes[sec]
      frac = (dup*1.0 / stot*1.0) * 100.0
      print(" %s %d (%2.1f%% of total %d)" % (sec, dup, frac, stot))

  if flag_dump_sym_alignment:
    print("\nGlobal alignment histogram for .text sections")
    for align, count in totfuncalign.items():
      print(" aligned to %d bytes: %d symbols" % (align, count))


def topsize_summary():
  """Report top symbols by size."""
  for secname, secdict in topsym_secdict.items():
    if secname not in insections:
      continue
    print("\nTop symbols in section \"%s\":" % secname)
    rawtups = []
    for sm, sz in secdict.items():
      tup = (sz, sm)
      rawtups.append(tup)
    stups = sorted(rawtups, reverse=True)
    for t in stups:
      print("%5d %s" % (t[0], t[1]))


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options] <ELF files>

    options:
    -a         dump symbol alignment summary info as part of layout analysis
    -S X       restrict analysis to only sections that begin with X (ex: -S .text)
    -L         include complete symbol listing in layout analysis
    -A         process all *.so files in $ANDROID_PRODUCT_OUT/symbols/system
    -H         image of interest is host and not target (testing/debugging)
    -R         report duplicates in each section (symbols with same name and size)
    -T N       report top symbols by size in each section
    -d         increase debug msg verbosity level
    -X         skip check to to make sure lib is in symbols dir
    -r {32,64} restrict analysis to just ELF-32 or just ELF-64 files

    Analyzes symbol (text and data) layout in the input ELF files, reporting
    any instances of inter-object padding and/or symbol duplication.

    Notes:
     - arguments are expected to be linked (.so or .exe) but unstripped

    """ % os.path.basename(sys.argv[0]))
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""

  global flag_examine_all_loadmodules, flag_check_in_symbols, flag_filemode
  global flag_report_duplicates, flag_input_files, apo, abt, insections
  global flag_dump_sym_alignment, flag_show_symbols, flag_restrict_elf
  global flag_report_topsize

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "adAHLRS:T:Xr:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-a":
      flag_dump_sym_alignment = 1
    elif opt == "-A":
      flag_examine_all_loadmodules = 1
    elif opt == "-H":
      flag_filemode = "host"
    elif opt == "-L":
      flag_show_symbols = 1
    elif opt == "-R":
      flag_report_duplicates = 1
    elif opt == "-T":
      topn = int(arg)
      if topn < 1:
        usage("supply a positive argument to -T option")
      flag_report_topsize = topn
    elif opt == "-r":
      if arg == "32":
        flag_restrict_elf = 32
      elif arg == "64":
        flag_restrict_elf = 64
      else:
        usage("argument to -r option must be either 32 or 64")
    elif opt == "-S":
      tomatch = arg
      pruned = {}
      for isec in insections:
        if isec.startswith(tomatch):
          pruned[isec] = 0
      if not list(pruned.keys()):
        usage("no interesting sections start with %s" % tomatch)
      u.verbose(1, "sections matching -S arg %s: %s" %
                (tomatch, " ".join(list(pruned.keys()))))
      insections = pruned
    elif opt == "-X":
      flag_check_in_symbols = 0

  if not args and flag_examine_all_loadmodules == 0:
    usage("specify at least one input file or use -A option")

  if args and flag_examine_all_loadmodules == 1:
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

parse_args()
u.setdeflanglocale()
fileargs = flag_input_files
if flag_examine_all_loadmodules:
  fileargs = collect_all_loadmodules()

for filearg in fileargs:
  examinefile(filearg)
layout_summary()
if flag_report_topsize:
  topsize_summary()
