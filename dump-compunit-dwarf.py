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
import os
import re
import shlex
import subprocess
import sys

import script_utils as u


# Restrict dump to comp unit containing offset X
flag_offset_to_find = None

# Load module to examine
flag_loadmodule = None

# What to run as 'objdump'
flag_objdump = None


def perform():
  """Main driver routine."""
  # Step 1: dump only compilation unit info.
  cmd = ("%s --dwarf=info "
         "--dwarf-depth=0 %s" % (flag_objdump, flag_loadmodule))
  u.verbose(1, "running: %s" % cmd)
  lines = u.docmdlines(cmd)
  cre = re.compile(r"^\s*Compilation Unit \@ offset 0x(\S+)\:\s*$")
  units = 0
  lo = -1
  hi = -1
  maxoff = -1
  selectoff = -1
  for line in lines:
    m = cre.match(line)
    if m:
      binoff = int(m.group(1), 16)
      if binoff <= flag_offset_to_find:
        lo = units
        selectoff = binoff
      if binoff > flag_offset_to_find:
        hi = units
        break
      maxoff = binoff
      units += 1
  if units == 0 or lo == -1:
    u.warning("no DWARF compile units in %s, dump aborted" % flag_loadmodule)
    return
  if hi == -1:
    u.warning("could not find CU with offset higher than %x; "
              "dumping last CU at offset %x" % (flag_offset_to_find, maxoff))

  # Step 2: issue the dump
  cmd = ("%s --dwarf=info "
         "--dwarf-start=%d %s" % (flag_objdump, selectoff, flag_loadmodule))
  u.verbose(1, "dump cmd is: %s" % cmd)
  args = shlex.split(cmd)
  mypipe = subprocess.Popen(args, stdout=subprocess.PIPE)
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
    -T Y  run 'objdump' via command Y

    Example usage:

    $ %s -m mprogram -x 0x40054

    """ % (me, me))

  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_offset_to_find, flag_loadmodule, flag_objdump

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "dm:x:T:")
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
  if not flag_offset_to_find:
    usage("specify offset to find with -x")

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
