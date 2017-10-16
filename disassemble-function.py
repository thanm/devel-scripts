#!/usr/bin/python
"""Disassemble a specific function from a load module.

"""

from collections import defaultdict
import getopt
from operator import itemgetter
import os
import re
import sys

import script_utils as u


# Echo command before executing
flag_echo = True

# Dry run mode
flag_dryrun = False

# Functions and load modules
flag_functions = {}
flag_loadmodules = {}

# Compile unit to look for in DWARF
flag_dwarf_cu = None

# Dump dwarf die chain
flag_dumpdwarf = False

# Begin-DIE preamble
bdiere = re.compile(r"^\s*\<\d+\>\<(\S+)\>\:\s*Abbrev\sNumber\:"
                    r"\s+(\d+)\s+\((\S+)\)\s*$")

# Within-DIE regex
indiere = re.compile(r"^(\s*)\<(\S+)\>(\s+)(DW_AT_\S+)(\s*)\:(.*)$")

# For grabbing dwarf ref from attr value
absore = re.compile(r"^\s*\<\S+\>\s+DW_AT_\S+\s*\:\s*\<0x(\S+)\>.*$")

# Misc
hexvalre = re.compile(r"^\s*0x(\S+)\s*$")

def docmd(cmd):
  """Execute a command."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmd(cmd)


def doscmd(cmd):
  """Execute a command."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.doscmd(cmd)


def docmderrout(cmd, outfile):
  """Execute a command."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmderrout(cmd, outfile)


def docmdout(cmd, outfile):
  """Execute a command to an output file."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmdout(cmd, outfile)


def grabaddrsize(line, func):
  """Grab address and size from objdump line if sym matches."""
  regexes = [re.compile(r"^(\S+)\s.+\s(\S+)\s+\.hidden\s+(\S+)$"),
             re.compile(r"^(\S+)\s.+\s(\S+)\s+(\S+)$")]
  hexstaddr = None
  hexsize = None
  for r in regexes:
    m = r.match(line)
    if m:
      name = m.group(3)
      if name == func:
        # Found
        hexstaddr = m.group(1)
        hexsize = m.group(2)
        break
  if hexstaddr and hexsize == "00000000":
    u.warning("warning -- malformed hexsize for func %s" % func)
    hexsize = "4"
  return (hexstaddr, hexsize)


def disas(func, tgt):
  """Disassemble a specified function."""
  u.verbose(1, "looking for %s in output of objdump -t %s" % (func, tgt))
  lines = u.docmdlines("objdump -t %s" % tgt)
  hexstaddr = None
  hexsize = None
  for line in lines:
    hexstaddr, hexsize = grabaddrsize(line, func)
    if hexstaddr:
      break
  if not hexstaddr:
    u.verbose(0, "... could not find %s in "
              "output of objdump, skipping" % func)
    return
  try:
    staddr = int(hexstaddr, 16)
    size = int(hexsize, 16)
    enaddr = staddr + size
  except ValueError:
    u.verbose(0, "... malformed staddr/size (%s, %s) "
              "for %s, skipping" % (hexstaddr, hexsize, func))
    return
  cmd = ("objdump --no-show-raw-insn --wide -dl "
         "--start-address=0x%x "
         "--stop-address=0x%x %s" % (staddr, enaddr, tgt))
  if flag_dwarf_cu and not flag_dryrun:
    lines = u.docmdlines(cmd)
    dodwarf(lines)
  else:
    docmd(cmd)


def read_die_chain(lines):
  """Reads output of objdump --dwarf=info."""
  # Maps beginning DIE offset to list of lines for DIE
  dies = defaultdict(list)
  curdieoff = None
  for line in lines:
    # Start of DIE?
    m1 = bdiere.match(line)
    if m1:
      absoff = m1.group(1)
      odec = int(absoff, 16)
      dies[odec].append(line)
      curdieoff = odec
      continue

    # Middle of DIE?
    m2 = indiere.match(line)
    if m2:
      dies[curdieoff].append(line)
      continue
  return dies


def expand_die(lines):
  """Expand/explode specified DIE."""

  # grab abbrev and tag from first line
  m1 = bdiere.match(lines[0])
  abbrev = 0
  tag = "undefined"
  if not m1:
    u.error("can'r apply bdiere match to %s" % lines[0])
  abbrev = m1.group(2)
  tag = m1.group(3)

  attrs = {}

  # Process remaining lines
  for line in lines[1:]:
    m2 = indiere.match(line)
    if not m2:
      u.error("can'r apply indiere match to %s" % line)
    attr = m2.group(4)
    val = m2.group(6).strip()
    attrs[attr] = val

  # return results
  return abbrev, tag, attrs


def grab_hex_attr(attrs, attrname):
  """Grab an attribute by value, convert from hex, return dec or -1"""
  if attrname in attrs:
    hexval = attrs[attrname]
    m1 = hexvalre.match(hexval)
    if m1:
      return int(m1.group(1), 16)
  return -1


def collect_die_nametag(attrs, off, tag, dies):
  """Collect human readable info on DIE."""

  # If DIE is named, then use that
  if "DW_AT_name" in attrs:
    return attrs["DW_AT_name"]

  # Not named -> look at abstract origin
  if "DW_AT_abstract_origin" in attrs:
    absoff = attrs["DW_AT_abstract_origin"]
    if absoff in dies:
      lines = dies[absoff]
      aabbrev, atag, aattrs = expand_die(lines)
      if "DW_AT_name" in aattrs:
        return aattrs["DW_AT_name"]

  # No success, return tag
  return "unknown@%s@%x" % (tag, off)


def get_pc_range(attrs):
  """Get HI/LO PC range from attributes."""
  lodec = grab_hex_attr(attrs, "DW_AT_low_pc")
  hidec = grab_hex_attr(attrs, "DW_AT_high_pc")
  return (lodec, hidec)


def collect_ranged_items(dies):
  """Collect items that have start/end ranges."""

  results = []

  for off, lines in dies.iteritems():
    abbrev, tag, attrs = expand_die(lines)

    # Does it have a PC range?
    lodec, hidec = get_pc_range(attrs)
    if lodec != -1 and hidec != -1:
      # Success. Call a helper to collect more info, and add to list
      name = collect_die_nametag(attrs, off, tag, dies)
      tup = (lodec, hidec, name)
      results.append(tup)

  return results


def dodwarf(asmlines):
  """Annotate disassembly with DWARF info."""
  lms = flag_loadmodules.keys()
  lm = lms[0]
  u.verbose(1, "inspecting DWARF for %s" % lm)

  # Initial pass to collect load modules
  lines = u.docmdlines("objdump --dwarf=info --dwarf-depth=1 %s" % lm)
  dies = read_die_chain(lines)

  cu_offset = None
  if flag_dwarf_cu != ".":
    # Try to find correct DWARF CU
    for off, lines in dies.iteritems():
      abbrev, tag, attrs = expand_die(lines)
      if tag != "DW_TAG_compile_unit":
        continue
      if "DW_AT_name" not in attrs:
        continue
      cuname = attrs["DW_AT_name"]
      if cuname == flag_dwarf_cu:
        u.verbose(1, "found DWARF %s cu at offset %s" % (flag_dwarf_cu, off))
        cu_offset = "--dwarf-start=%d" % off

  # Bail if not match
  ranged_items = []
  if not cu_offset:
    u.warning("could not locate DWARF compilation unit %s" % flag_dwarf_cu)
  else:
    # Redo dwarf dump with selected unit
    lines2 = u.docmdlines("objdump %s --dwarf=info %s" % (cu_offset, lm))
    dies = read_die_chain(lines2)

    # Dump
    if flag_dumpdwarf:
      for off in sorted(dies):
        dlines = dies[off]
        abbrev, tag, attrs = expand_die(dlines)
        u.verbose(2, "DIE at offset %s: abbrev %s "
                  "tag %s" % (off, abbrev, tag))
        for attr, val in attrs.iteritems():
          u.verbose(2, " %s => %s" % (attr, val))

    # Collect ranged items
    ranged_items = collect_ranged_items(dies)

  # ASM re
  asmre = re.compile(r"(^\s*)(\S+)(\:\s*\S.*)$")

  # Output
  for line in asmlines:

    m1 = asmre.match(line)
    if not m1:
      sys.stdout.write(line)
      sys.stdout.write("\n")
      continue

    sp = m1.group(1)
    addr = m1.group(2)
    rem = m1.group(3)

    try:
      decaddr = int(addr, 16)
    except ValueError:
      sys.stdout.write(line)
      sys.stdout.write("\n")
      continue

    suffixes = []

    # Assumes smallish functions -- replace with something more
    # efficient if this assumption doesn't hold.
    for tup in ranged_items:
      lo, hi, name = tup
      if lo == decaddr:
        suffixes.append(" begin %s" % name)
      if hi == decaddr:
        suffixes.append(" end %s" % name)

    sys.stdout.write("%s%s%s" % (sp, addr, rem))
    if suffixes:
      sys.stdout.write(" // ")
      sys.stdout.write(",".join(suffixes))
    sys.stdout.write("\n")


def perform():
  """Main routine for script."""
  for m in flag_loadmodules:
    for f in flag_functions:
      disas(f, m)


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options]

    options:
    -e    echo commands before executing
    -d    increase debug msg verbosity level
    -D    dryrun mode (echo commands but do not execute)
    -f F  dump function F
    -m M  in load module M
    -W X  read and incorporate DWARF from compile unit X
          (if X is ".", read all compile units)
    -Z    dump dwarf DIE chain

    Example usage:

    $ %s -f bytes.ReadFrom.pN12_bytes.Buffer -m libgo.so.10.0.0

    """ % (me, me)

  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_echo, flag_dryrun, flag_dwarf_cu, flag_dumpdwarf

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "deDf:m:W:Z")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  if args:
    usage("unknown extra args")

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-D":
      u.verbose(0, "+++ dry run mode")
      flag_dryrun = True
      flag_echo = True
    elif opt == "-e":
      flag_echo = True
    elif opt == "-f":
      flag_functions[arg] = 1
    elif opt == "-m":
      flag_loadmodules[arg] = 1
    elif opt == "-W":
      flag_dwarf_cu = arg
    elif opt == "-Z":
      flag_dumpdwarf = True

  # Make sure at least one function, loadmodule
  if not flag_functions:
    usage("specify function name with -f")
  if not flag_loadmodules:
    usage("specify loadmodule with -m")
  if len(flag_loadmodules) > 1 and flag_dwarf_cu:
    usage("use only single loadmodule with -W option")


#
#......................................................................
#
# Main portion of script
#
parse_args()
u.setdeflanglocale()
perform()
exit(0)
