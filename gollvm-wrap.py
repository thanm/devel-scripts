#!/usr/bin/python
"""Selectively runs gollvm instead of gccgo.

This is a shim script that intercepts invocations of 'gccgo' and then
in turn invokes either the real gccgo driver or a copy of gollvm
instead, depending on the arguments and on environment variables.

When performing a Go build with gccgo, the Go command will typically
invoke gccgo once for each compilation step, which might look like

  gccgo -I ... -o objfile.o -g <options> file.go file2.go ... fileN.go

and then a final invocation will be made at the link step, e.g.

  gccgo -L ... somearchive.a ... -o binary

The goal of this shim is to convert invocations of the first form to
llvm-goparse invocations, and to ignore invocations of the second form
and just pass them on to gccgo.

We also tack on a set of additional "-L" options to the llvm-goparse
invocation so that it can find the go runtime libraries, and intercept
the "-o" option so that we can run the asembler afterwards.
"""

import getopt
import os
import re
import subprocess
import sys

import script_utils as u

# Echo command before executing
flag_echo = True

# Dry run mode
flag_dryrun = False

# gccgo only mode
flag_nollvm = False


def form_golibargs(driver):
  """Form correct go library args."""
  ddir = os.path.dirname(driver)
  bdir = os.path.dirname(ddir)
  cmd = "find %s/lib64 -name runtime.gox -print" % bdir
  lines = u.docmdlines(cmd)
  if not lines:
    u.error("no output from %s -- bad gccgo install dir?" % cmd)
  line = lines[0]
  rdir = os.path.dirname(line)
  u.verbose(1, "libdir is %s" % rdir)
  return ["-L", rdir]


def perform():
  """Main driver routine."""

  u.verbose(1, "argv: %s" % " ".join(sys.argv))

  # Perform a walk of the command line arguments looking for Go files.
  reg = re.compile(r"^\S+\.go$")
  foundgo = False
  for clarg in sys.argv[1:]:
    m = reg.match(clarg)
    if m:
      foundgo = True
      break

  if not foundgo or flag_nollvm:
    # No go files. Invoke real gccgo.
    bd = os.path.dirname(sys.argv[0])
    driver = "%s/gccgo.real" % bd
    u.verbose(1, "driver path is %s" % driver)
    args = [sys.argv[0]] + sys.argv[1:]
    u.verbose(1, "args: '%s'" % " ".join(args))
    os.execv(driver, args)
    u.error("exec failed: %s" % driver)

  # Create a set of massaged args.
  nargs = []
  skipc = 0
  outfile = None
  asmfile = None
  for ii in range(1, len(sys.argv)):
    clarg = sys.argv[ii]
    if skipc != 0:
      skipc -= 1
      continue
    if clarg == "-o":
      skipc = 1
      outfile = sys.argv[ii+1]
      asmfile = "%s.s" % outfile
      nargs.append("-o")
      nargs.append(asmfile)
      continue
    nargs.append(clarg)

  if not asmfile or not outfile:
    u.error("fatal error: unable to find -o "
            "option in clargs: %s" % " ".join(sys.argv))
  golibargs = form_golibargs(sys.argv[0])
  nargs += golibargs
  u.verbose(1, "revised args: %s" % " ".join(nargs))

  # Invoke gollvm.
  driver = "llvm-goparse"
  u.verbose(1, "driver path is %s" % driver)
  nargs = ["llvm-goparse"] + nargs
  rc = subprocess.call(nargs)
  if rc != 0:
    u.verbose(1, "return code %d from %s" % (rc, " ".join(nargs)))
    return 1

  # Invoke the assembler
  ascmd = "as %s -o %s" % (asmfile, outfile)
  u.verbose(1, "asm command is: %s" % ascmd)
  rc = u.docmdnf(ascmd)
  if rc != 0:
    u.verbose(1, "return code %d from %s" % (rc, ascmd))
    return 1

  # Success
  return 0


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s <gccgo args>

    Options (via GOLLVM_WRAP_OPTIONS):
    -d    increase debug msg verbosity level
    -e    show commands being invoked
    -D    dry run (echo cmds but do not execute)
    -G    pure gccgo compile (no llvm-goparse invocations)

    """ % os.path.basename(sys.argv[0])
  sys.exit(1)


def parse_env_options():
  """Option parsing from env var."""
  global flag_echo, flag_dryrun, flag_nollvm

  optstr = os.getenv("GOLLVM_WRAP_OPTIONS")
  if not optstr:
    return
  args = optstr.split()

  try:
    optlist, _ = getopt.getopt(args, "deDG")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, _ in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-e":
      flag_echo = True
    elif opt == "-D":
      flag_dryrun = True
    elif opt == "-G":
      flag_nollvm = True
  u.verbose(1, "env var options parsing complete")


# Setup
u.setdeflanglocale()
parse_env_options()
prc = perform()
sys.exit(prc)
