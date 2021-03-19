#!/usr/bin/python3
"""Wrap a code or assembly dump in HTML for viewing.

Read a file X and emit X.html that has nice formatting, with
line numbers.

"""

import cgi
import getopt
import os
import sys

import script_utils as u

# Files to process
infiles = {}

# Exit status
exit_st = 0


def emit(outf, infile, lines):
  """Emit lines for file."""
  preamble = """\

<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
        "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head>

<style type="text/css">

body {
  background-color: #eee;
  color: #555;
}

pre {
  font-family: monospace;
  background-color: #fff;
  padding: 0.5em;
}

pre {
  counter-reset: linecounter;
}

pre span.line {
  counter-increment: linecounter;
}

pre span.line:before{
  content: counter(linecounter);
  width: 2em;
  display: inline-block;
}

</style>

<title>%s</title>

</head>

<h2>%s</h2>
<p>

<body>

<div class="container">
<pre>

""" % (infile, infile)

  outf.write(preamble)
  lc = 1
  for line in lines:
    outf.write("<span class=line id=\"L%d\"> "
               "%s</span>\n" % (lc, cgi.escape(line.rstrip())))
    lc += 1
  outf.write("</pre>\n")
  outf.write("</div>\n")
  outf.write("</body>\n")


def process_file(infile):
  """Process a file."""
  lines = []
  try:
    with open(infile, "r") as rf:
      lines = rf.readlines()
  except IOError:
    u.verbose(0, "open failed for %s, skipping" % infile)
    return 1
  outfile = "%s.html" % infile
  wf = None
  try:
    with open(outfile, "w") as wf:
      emit(wf, infile, lines)
  except IOError:
    u.verbose(0, "open for write failed for %s, skipping" % outfile)
    return 1
  return 0


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options] <files>

    options:
    -d    increase debug msg verbosity level

    Opens each specified file F, reads it, and emits a file
    F.html with formatting.

    """ % os.path.basename(sys.argv[0]))
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "d")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, _ in optlist:
    if opt == "-d":
      u.increment_verbosity()

  if not args:
    usage("supply one or more input files")
  for a in args:
    infiles[a] = 1


u.setdeflanglocale()
parse_args()
for inf in infiles:
  st = process_file(inf)
  if st:
    exit_st = 1
exit(exit_st)
