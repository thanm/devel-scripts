#!/usr/bin/python3
"""Generate C code with high register pressure.

"""

import getopt
import os
import sys

import script_utils as u


flag_copies = 4


def emit_decl(v):
  """Emit var decl."""
  for ii in range(0, flag_copies):
    sys.stdout.write("  ull %s%d;\n" % (v, ii))


def emit_vinit(v, salt):
  """Emit var init."""
  for ii in range(0, flag_copies):
    sys.stdout.write("  %s%d = ar[(qx & %s) + %d];\n" % (v, ii, salt, ii))


def emit_binop(v1, v2, v3):
  """Emit bin op."""
  for ii in range(0, flag_copies):
    sys.stdout.write("  %s%d = %s%d - %s%d;\n" % (v1, ii, v2, ii, v3, ii))


def emit_trinop(v1, v2, v3, v4, v5):
  """Emit trin op."""
  for ii in range(0, flag_copies):
    sys.stdout.write("  %s%d = (%s%d - %s%d) ^ "
                     "(%s%d + %s%d) ;\n" % (v1, ii, v2, ii,
                                            v3, ii, v4, ii,
                                            v5, ii))


def emit_bitp(v1, v2, v3, c):
  """Emit bitpick op."""
  for ii in range(0, flag_copies):
    sys.stdout.write("  %s%d = %s%d | (%s%d & %s) "
                     ";\n" % (v1, ii, v2, ii, v3, ii, c))


def emit_store(v):
  """Emit store."""
  for ii in range(0, flag_copies):
    sys.stdout.write("  ar[%d] = %s%d;\n" % (ii, v, ii))


def perform():
  """Emit C code."""
  sys.stdout.write("\ntypedef unsigned ull;\n")
  sys.stdout.write("ull foo(ull *ar, ull qx) {\n\n")
  sys.stdout.write("  ull lcv = 100;\n")

  # Declare
  thevars = ["t", "q", "r", "s", "u"]
  for v in thevars:
    emit_decl(v)

  # Init t, q, r
  emit_vinit("t", "19")
  emit_vinit("q", "121")
  emit_vinit("r", "117")

  # q = q - t
  emit_binop("q", "q", "t")

  # define s
  emit_vinit("s", "17")

  # loop
  sys.stdout.write("\n  while(lcv--) {\n")

  # r = (r - q) ^ (q - s)
  emit_trinop("r", "r", "q", "q", "s")
  # s = s + r
  emit_binop("s", "s", "r")

  sys.stdout.write("  }\n")

  # define u
  emit_vinit("u", "0xff")

  # u = u | (s & c)
  emit_bitp("u", "u", "s", "7")

  # store u
  emit_store("u")

  # that's it
  sys.stdout.write("  return 0;\n")
  sys.stdout.write("}\n")


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options]

    options:
    -d    increase debug msg verbosity level
    -c N  set number of copies to N (def: 4)

    """ % os.path.basename(sys.argv[0]))
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_copies

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "dc:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  if args:
    usage("uknown extra args")
  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-c":
      flag_copies = int(arg)


# Setup
u.setdeflanglocale()
parse_args()

# Main guts
perform()
