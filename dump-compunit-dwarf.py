#!/usr/bin/python3
"""Dump DWARF for single compile unit.

Given a DIE offset O in hex format and a load module, use objdump to dump the
DWARF for the load module, restricting the dump to the single compilation unit
containing the offset O.

The intent here is to easily emit the small section of DWARF containing the DIE
of interest (which has presumably turned up in an assert or been identified via
some other mechanism). DWARF dumps for large (or even medium-sized) C++ programs
can be enormous, so it helps to be able to capture just a single compilation
unit's worth of the .debug_info.
"""

import getopt
import locale
import os
import re
import shlex
import subprocess
import sys

import script_utils as u


# Restrict dump to comp unit containing offset X
flag_offset_to_find = None

# Restrict dump to comp unit with name X
flag_name_to_find = None

# Load module to examine
flag_loadmodule = None

# What to run as 'objdump'
flag_objdump = None

# Include line table dump
flag_dumpline = False


def perform():
  """Main driver routine."""
  depth = 0 if flag_offset_to_find else 1
  # Step 1: dump only compilation unit info.
  cmd = ("%s --dwarf=info "
         "--dwarf-depth=%d %s" % (flag_objdump, depth, flag_loadmodule))
  u.verbose(1, "running: %s" % cmd)
  lines = u.docmdlines(cmd)
  cre = re.compile(r"^\s*Compilation Unit \@ offset 0x(\S+)\:\s*$")
  namere = re.compile(r"^\s+\<\S+\>\s+DW_AT_name\s+\:\s+(\S+)\s*$")
  stlre = re.compile(r"^\s+\<\S+\>\s+DW_AT_stmt_list\s+\:\s+(\S+)\s*$")
  units = 0
  lo = -1
  hi = -1
  binoff = 0
  maxoff = -1
  selectoff = -1
  stlist = 0
  found = False
  for line in lines:
    u.verbose(3, "line is: %s" % line)
    m = cre.match(line)
    if m:
      binoff = int(m.group(1), 16)
      if flag_offset_to_find:
        if binoff <= flag_offset_to_find:
          lo = units
          selectoff = binoff
          found = True
        if binoff > flag_offset_to_find:
          hi = units
          break
      maxoff = binoff
      units += 1
    if flag_name_to_find:
      m2 = namere.match(line)
      if m2:
        if m2.group(1) == flag_name_to_find:
          selectoff = binoff
          found = True
    if flag_dumpline:
      m3 = stlre.match(line)
      if m3:
        if selectoff == binoff:
          stlist = m3.group(1)

  if units == 0:
    u.warning("no DWARF compile units in %s, dump aborted" % flag_loadmodule)
    return
  if flag_offset_to_find and hi == -1:
    u.warning("could not find CU with offset higher than %x; "
              "dumping last CU at offset %x" % (flag_offset_to_find, maxoff))
  if flag_name_to_find and not found:
    u.error("could not find CU with name %s" % flag_name_to_find)

  # Step 2: issue the .debug_info dump
  cmd = ("%s --dwarf=info "
         "--dwarf-start=%d %s" % (flag_objdump, selectoff, flag_loadmodule))
  u.verbose(1, "dump cmd is: %s" % cmd)
  args = shlex.split(cmd)
  enc = locale.getdefaultlocale()[1]
  mypipe = subprocess.Popen(args, stdout=subprocess.PIPE, encoding=enc)
  cure = re.compile(r"^.+\(DW_TAG_compile_unit\).*")
  ncomps = 0
  while True:
    line = mypipe.stdout.readline()
    if not line:
      break
    m = cure.match(line)
    if m:
      ncomps += 1
      if ncomps > 1:
        break
    sys.stdout.write(line)

  if not flag_dumpline:
    return

  # Step 3: issue the .debug_line dump. This can be expensive, since
  # the --dwarf-start option doesn't apply.
  cmd = ("%s --dwarf=rawline %s" % (flag_objdump, flag_loadmodule))
  offre = re.compile(r"^\s+Offset:\s+(\S+)\s*$")
  u.verbose(1, "dump cmd is: %s" % cmd)
  args = shlex.split(cmd)
  enc = locale.getdefaultlocale()[1]
  mypipe = subprocess.Popen(args, stdout=subprocess.PIPE, encoding=enc)
  suppressed = True
  ncomps = 0
  sys.stdout.write("\n\n.debug_line dump:\n\n")
  while True:
    line = mypipe.stdout.readline()
    if not line:
      break
    m = offre.match(line)
    if m:
      if m.group(1) == stlist:
        suppressed = False
      else:
        if not suppressed:
          break
    if not suppressed:
      sys.stdout.write(line)


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options]

    options:
    -d    increase debug msg verbosity level
    -m M  input load module is M
    -x X  dump only compilation unit containing DIE with offset O
    -n P  dump only compilation unit with DW_AT_name equal to 'P'
    -T Y  run 'objdump' via command Y
    -L    dump out line table for compilation unit as well

    Example usage:

    // Dump out compilation unit containing DIE with offset 0x40054
    $ %s -m mprogram -x 0x40054

    // Dump out compilation unit 'mypackage' with line table
    $ %s -m mprogram -n mypackage -L

    """ % (me, me, me))

  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_offset_to_find, flag_loadmodule, flag_objdump
  global flag_dumpline, flag_name_to_find

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "dLn:m:x:T:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  if args:
    usage("unknown extra args")

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-T":
      flag_objdump = arg
    elif opt == "-L":
      flag_dumpline = True
    elif opt == "-n":
      flag_name_to_find = arg
    elif opt == "-x":
      r = re.compile(r"^0x(\S+)$")
      m = r.match(arg)
      if not m:
        usage("supply argument of the form 0x<hexliteral> to -x option")
      hexdigits = m.group(1)
      try:
        v = int(hexdigits, 16)
      except ValueError:
        usage("supply argument of the form 0x<hexliteral> to -x option")
      u.verbose(1, "restricting output to compunit "
                   "containing DIE offset %x\n" % v)
      flag_offset_to_find = v
    elif opt == "-m":
      if not os.path.exists(arg):
        usage("argument '%s' to -m option does not exist" % arg)
      flag_loadmodule = arg

  # Make sure at least one function, loadmodule
  if not flag_loadmodule:
    usage("specify loadmodule -m")
  if flag_offset_to_find and flag_name_to_find:
    usage("specify at most one of -x and -n")
  if not flag_offset_to_find and not flag_name_to_find:
    usage("specify offset to find with -x or name to find with -n")

  # Pick objdump variant based on Os.
  if not flag_objdump:
    lines = u.docmdlines("uname")
    if not lines:
      u.error("unable to run/interpret 'uname'")
    if lines[0] == "Darwin":
      flag_objdump = "gobjdump"
    else:
      flag_objdump = "objdump"


#
#......................................................................
#
# Main portion of script
#
parse_args()
u.setdeflanglocale()
perform()
exit(0)
