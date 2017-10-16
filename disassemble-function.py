#!/usr/bin/python
"""Disassemble a specific function from a load module.

"""

import getopt
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
  docmd("objdump --wide -dl --start-address=0x%x "
        "--stop-address=0x%x %s" % (staddr, enaddr, tgt))


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

    Example usage:

    $ %s -f bytes.ReadFrom.pN12_bytes.Buffer -m libgo.so.10.0.0

    """ % (me, me)

  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_echo, flag_dryrun

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "deDf:m:")
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

  # Make sure at least one function, loadmodule
  if not flag_functions:
    usage("specify function name with -f")
  if not flag_loadmodules:
    usage("specify loadmodule with -m")


#
#......................................................................
#
# Main portion of script
#
parse_args()
u.setdeflanglocale()
perform()
exit(0)
