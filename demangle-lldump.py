#!/usr/bin/python3
"""Filter to demangle llvm asm dumps.

Reads stdin, tries to demangle every @ symbol.

"""

import getopt
import os
import re
import sys
import tempfile

import script_utils as u

# Input and output file (if not specified, defaults to stdin/stdout)
flag_infile = None
flag_outfile = None

# Demangler program to use
flag_demangler = "c++filt"

#......................................................................

# Regular expressions to match:

# define internal zeroext i1 @_ZL7docallsI2I4EbT_(i32 %p1.coerce) #0 {
funcre = re.compile(r"^define(\s.+)\@(\S+)\((.*)\)(\s.*)\{\s*$")

# %call = call zeroext i1 @_ZL7docallsI2I4EbT_(i32 %4) #3
callre = re.compile(r"^(.+)\scall\s(.*)\@(\S+)\((.*)(\).*)$")


def perform_demangle(inf, outf):
  """Read inf and demangle contents to outf."""

  delflag = False
  todemtf = tempfile.NamedTemporaryFile(mode="w",
                                        prefix="todemangle",
                                        delete=delflag)
  demres = "%s.res" % todemtf.name

  # First pass to collect things to demangle
  lines = inf.readlines()
  symcount = 0
  for line in lines:
    chunks = line.split()
    if chunks and chunks[0] == "define":
      fdm = funcre.match(line)
      if fdm:
        sym = fdm.group(2)
        u.verbose(2, "writing to temp file: %s" % sym)
        todemtf.write("%s\n" % sym)
        symcount += 1
      continue
    hascall = False
    for c in chunks:
      if c == "call":
        hascall = True
    if hascall:
      cm = callre.match(line)
      if cm:
        sym = cm.group(3)
        u.verbose(2, "writing to temp file: %s" % sym)
        todemtf.write("%s\n" % sym)
        symcount += 1
      continue
  todemtf.close()

  # Run demangler on temp file
  cmd = "%s < %s > %s" % (flag_demangler, todemtf.name, demres)
  u.verbose(2, "demangle command is: %s" % cmd)
  rc = u.docmdinout(flag_demangler, todemtf.name, demres)
  if rc != 0:
    u.error("error invoking command: %s" % cmd)

  # Read demangler output
  results = []
  try:
    with open(demres, "r") as infile:
      results = infile.readlines()
  except IOError as e:
    u.error("unable to temp file output %s from demangler: "
            "%s" % (demres, e.strerror))
  for r in results:
    u.verbose(2, "result: %s" % r.strip())
  os.unlink(todemtf.name)
  os.unlink(demres)

  # Check to make sure number of results is sane
  if len(results) != symcount:
    u.error("expected %d results, got %d" % (symcount, len(results)))

  # Second pass to integrate in the results
  counter = 0
  for line in lines:
    chunks = line.split()
    if chunks and chunks[0] == "define":
      fdm = funcre.match(line)
      if fdm:
        preamble = fdm.group(1)
        mid1 = fdm.group(3)
        mid2 = fdm.group(4)
        demangled = results[counter]
        demangled = demangled.strip()
        u.verbose(2, "dem %s => %s" % (fdm.group(3), demangled))
        outf.write("define%s@\"%s\"(%s)%s{\n" % (preamble, demangled, mid1, mid2))
        counter += 1
        continue
    hascall = False
    for c in chunks:
      if c == "call":
        hascall = True
    if hascall:
      cm = callre.match(line)
      if cm:
        pre1 = cm.group(1)
        pre2 = cm.group(2)
        cargs = cm.group(4)
        post = cm.group(5)
        demangled = results[counter]
        demangled = demangled.strip()
        u.verbose(2, "dem %s => %s" % (cm.group(3), demangled))
        outf.write("%s call %s@%s(%s%s\n" % (pre1, pre2, demangled,
                                              cargs, post))
        counter += 1
        continue

      continue

    outf.write(line)


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
  perform_demangle(inf, outf)
  if flag_infile:
    inf.close()
  if flag_outfile:
    outf.close()


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options] < input > output

    options:
    -d    increase debug msg verbosity level
    -i F  read from input file F
    -o G  write to output file O
    -x D  use demangler program D

    """ % me)
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_infile, flag_outfile, flag_demangler

  try:
    optlist, _ = getopt.getopt(sys.argv[1:], "di:o:x:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-i":
      flag_infile = arg
    elif opt == "-o":
      flag_outfile = arg
    elif opt == "-x":
      flag_demangler = arg


parse_args()
u.setdeflanglocale()
perform()
