#!/usr/bin/python
"""Post-process a GC roots dump.
"""

import getopt
import os
import re
import sys

import script_utils as u

# Input and output file (if not specified, defaults to stdin/stdout)
flag_infile = None
flag_outfile = None

# Binary to analyze
flag_module = None

#......................................................................

# Regular expressions to match:

# Start of root collection
rcstartre = re.compile(r"^root collection\s+(\d+)\s*$")

# Root list entry
rlere = re.compile(r"^\s*\d+\s+\:\s+0x(\S+)\s+(\d+)\s*$")


def perform_filt(inf, outf):
  """Read inf and emit summary to outf."""

  ncollections = 0
  nroots = 0
  collections = []
  elist = []
  addrsize = {}

  # Read input
  while True:
    line = inf.readline()
    if not line:
      break
    u.verbose(3, "line is %s" % line)

    # Root collection start?
    m1 = rcstartre.match(line)
    if m1:
      collections.append(elist)
      elist = []
      ncollections += 1
      continue

    # Root list entry?
    m2 = rlere.match(line)
    if m2:
      nroots += 1
      hexaddr = m2.group(1)
      siz = m2.group(2)
      addrsize[hexaddr] = int(siz)
      elist.append(hexaddr)
      continue

  if elist:
    collections.append(elist)

  # Now that we've read everything, write GDB script.
  if os.path.exists("gdb-cmds.txt"):
    os.unlink("gdb-cmds.txt")
  if os.path.exists("gdb-out.txt"):
    os.unlink("gdb-out.txt")
  try:
    gf = open("gdb-cmds.txt", "wb")
  except IOError as e:
    u.error("unable to open output file 'gdbcmds.txt': %s" % e.strerror)
  gf.write("set height 0\n")
  gf.write("set width 0\n")
  gf.write("set pagination off\n")
  gf.write("set logging file gdb-out.txt\n")
  gf.write("set logging on\n")
  gf.write("file %s\n" % flag_module)
  ncol = 0
  for el in collections:
    gf.write("print \"collection %d\"\n" % ncol)
    ncol += 1
    for hexaddr in el:
      gf.write("print \"0x%x size %d\"\n" % (int(hexaddr, 16), addrsize[hexaddr]))
      gf.write("info sym 0x%s\n" % hexaddr)
  gf.close()

  # Invoke GDB
  u.docmd("gdb -batch -nh -x gdb-cmds.txt")

  # Emit
  try:
    rf = open("gdb-out.txt", "r")
  except IOError as e:
    u.error("unable to open output file 'gdb-out.txt': %s" % e.strerror)
  lines = rf.readlines()
  rf.close()
  for line in lines:
    outf.write(line)
  outf.close()
  u.verbose(0, "processed %d roots in %d collections" % (nroots, ncollections))


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
  perform_filt(inf, outf)
  if flag_infile:
    inf.close()
  if flag_outfile:
    outf.close()


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options] < input > output

    options:
    -d    increase debug msg verbosity level
    -i F  read from input file F
    -o G  write to output file O
    -m M  analyze load module M

    """ % me
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_infile, flag_outfile, flag_module

  try:
    optlist, _ = getopt.getopt(sys.argv[1:], "di:o:m:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-i":
      flag_infile = arg
    elif opt == "-m":
      flag_module = arg
    elif opt == "-o":
      flag_outfile = arg


parse_args()
u.setdeflanglocale()
perform()
