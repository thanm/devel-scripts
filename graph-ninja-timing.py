#!/usr/bin/python
"""Creates DOT graph to visualize ninja build timing.

Given a ninja build directoy, this program uses the tools from

 https://github.com/catapult-project/catapult.git
 https://github.com/nico/ninjatracing.git

to post-process the ".ninja_log" file into an execution trace that can
then be plotted and viewed on a web browser.

"""

import getopt
import os
import sys

import script_utils as u

# Output html file
flag_outfile = "trace.html"

# Path to "ninjatracing" repo
flag_ninjatracing = "/ssd2/ninjatracing/ninjatracing"

# Path to "catapult" repo
flag_catapult = "/ssd2/catapult"

# Dryrun, echo flags
flag_echo = False
flag_dryrun = False


def perform():
  """Main driver routine."""

  # Check for existence of ninja log file
  if not os.path.exists(".ninja_log"):
    u.error("unable to access .ninja_log file")

  # Generate json file from ninja log
  if flag_dryrun or flag_echo:
    u.verbose(0, "%s .ninja_log > trace.json" % flag_ninjatracing)
  if not flag_dryrun:
    u.docmdout("%s .ninja_log" % flag_ninjatracing, "trace.json")

  # Generate trace.html file from json
  cmd = ("%s/tracing/bin/trace2html trace.json "
         "--output=%s" % (flag_catapult, flag_outfile))
  if flag_dryrun or flag_echo:
    u.verbose(0, cmd)
  if not flag_dryrun:
    u.docmd(cmd)


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options] [-o output]

    options:
    -d    increase debug msg verbosity level
    -D    dry run mode (echo commands but do not execute)
    -o F  write output HTML to file F
    -C C  use catapult repo in directory C
    -N N  use ninjatracing repo in directory N

    Default output file (if -o option not used) is 'trace.html'.

    """ % os.path.basename(sys.argv[0])
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_outfile, flag_echo, flag_dryrun
  global flag_ninjatracing, flag_catapult

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "edDo:N:C:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  if args:
    usage("extra unknown arguments")
  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-D":
      flag_dryrun = True
    elif opt == "-e":
      flag_echo = True
    elif opt == "-N":
      flag_ninjatracing = arg
    elif opt == "-C":
      flag_catapult = arg
    elif opt == "-o":
      flag_outfile = arg

# Setup
u.setdeflanglocale()
parse_args()
perform()
