#!/usr/bin/python
"""Generate C++ code and makefile for large C++ shared lib.

"""

import getopt
import os
import sys

import script_utils as u

# Classes per instance
flag_num_classes = 100

# Number of instances
flag_num_instances = 100


def perform():
  """Emit files."""
  u.verbose(1, "emitting makefile.generated")
  mf = open("makefile.generated", "w")

  # divide instances into chunks by 10
  chunks = flag_num_instances / 10
  chunksize = 10
  jj = 0
  for ch in range(chunks):
    mf.write("OBJECTS%s =" % ch)
    for ii in range(chunksize):
      mf.write(" i%d_generated.o i%d_usegen.o" % (jj, jj))
      jj += 1
    mf.write("\n")

  # all objects
  mf.write("OBJECTS =")
  for ch in range(chunks):
    mf.write(" $(OBJECTS%d)" % ch)

  # emit a series of partial targets by chunk
  mf.write("\n")
  for kk in range(chunks):
    mf.write("\ngenerated-%d-%d.so:" % (0, kk))
    for ii in range(0, kk+1):
      mf.write(" $(OBJECTS%d)" % ii)
    mf.write("\n")
    mf.write("\t$(CXX) $(CXXFLAGS) $? -shared -o $@\n")

  # the big one
  mf.write("\n")
  mf.write("generated.so: $(OBJECTS)\n")
  mf.write("\t$(CXX) $(CXXFLAGS) $? -shared -o $@\n")

  # and some pseudo-targets
  mf.write("\n")
  mf.write("\nallgen:")
  kk = 0
  for ii in range(chunks):
    if kk+1 > chunks:
      kk = chunks-1
      mf.write(" generated-%d-%d.so" % (0, kk))
      break
    mf.write(" generated-%d-%d.so" % (0, kk))
    kk += 2
  mf.write("\n")
  mf.write("\n")
  mf.write("\nallobjs: $(OBJECTS)\n")
  mf.close()

  # the source code
  for ii in range(flag_num_instances):
    u.docmd("gencode_classes.py -c %s -C i%d_ -F "
            "i%d\n" % (flag_num_classes, ii, ii))


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options]

    options:
    -d    increase debug msg verbosity level
    -c N  emit N classes (def: 500) per instances
    -I N  emit N instances

    """ % os.path.basename(sys.argv[0])
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_num_classes, flag_num_instances

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "dc:I:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  if args:
    usage("uknown extra args")
  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-c":
      flag_num_classes = int(arg)
    elif opt == "-I":
      flag_num_instances = int(arg)


# Setup
u.setdeflanglocale()
parse_args()

# Main guts
perform()
