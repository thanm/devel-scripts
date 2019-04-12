#!/usr/bin/python3
"""Script to generate pprof CPU profile reports from a set of data files.

"""

import getopt
import os
import shutil
import sys
import tempfile

import script_utils as u

# Echo command before executing
flag_echo = True

# Dry run mode
flag_dryrun = False

# Input files
flag_infiles = []

# Output dir
flag_outdir = None

# Binary to analyze
flag_binary = None

# Tag to apply to output files.
flag_tag = None

# Generate mem profile variants if set.
flag_memvariants = False

# Path to pprof
flag_pprof_path = "pprof"


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


def docmdout(cmd, outfile):
  """Execute a command to an output file."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmdout(cmd, outfile)


def docmdinout(cmd, infile, outfile):
  """Execute a command reading from input file and writing to output file."""
  if flag_echo:
    sys.stderr.write("executing: %s < %s > %s\n" % (cmd, infile, outfile))
  if flag_dryrun:
    return
  u.docmdinout(cmd, infile, outfile)


def copydir(src, dst):
  """Copy directory."""
  if flag_echo:
    sys.stderr.write("copying dir %s to dir %s\n" % (src, dst))
  if flag_dryrun:
    return
  shutil.copytree(src, dst)


def rmdir(src):
  """Remove directory."""
  if flag_echo:
    sys.stderr.write("removing dir %s\n" % src)
  if flag_dryrun:
    return
  shutil.rmtree(src)


def rmfile(afile):
  """Remove a file."""
  if flag_echo:
    sys.stderr.write("removing file %s\n" % afile)
  if flag_dryrun:
    return
  os.unlink(afile)


def dochdir(thedir):
  """Switch to dir."""
  if flag_echo:
    sys.stderr.write("cd " + thedir + "\n")
  if flag_dryrun:
    return
  try:
    os.chdir(thedir)
  except OSError as err:
    u.error("chdir failed: %s" % err)


def dormdir(thedir):
  """Remove dir."""
  if flag_echo:
    sys.stderr.write("rm -r " + thedir + "\n")
  if flag_dryrun:
    return
  if not os.path.exists(thedir):
    return
  try:
    rmdir(thedir)
  except OSError as err:
    u.error("rmdir(%s) failed: %s" % (thedir, err))


def perform():
  """Main driver routine."""

  vnames = ["alloc_space", "inuse_space", "alloc_objects", "inuse_objects"]
  infixes = []
  if flag_tag:
    infixes = flag_tag
  variants = []
  if flag_memvariants:
    for v in vnames:
      infixes = [v]
      if flag_tag:
        infixes = [flag_tag, v]
      variants.append([v, infixes])
  else:
    infixes = []
    if flag_tag:
      infixes = [flag_tag]
    variants.append(["", infixes])

  for v in variants:
    ppopt = v[0]
    infixes = v[1]

    # Emit temp file to use for pprof input
    try:
      scriptf = tempfile.NamedTemporaryFile(mode="w", delete=True)
      outf = tempfile.NamedTemporaryFile(mode="w", delete=True)
      ppo = open(scriptf.name, "w")
    except IOError:
      u.verbose(0, "open failed for %s" % outf.name)
    u.verbose(1, "opened tempfile %s" % outf.name)

    profiles = {}
    pnames = ["top15", "top100", "svg", "tree", "raw"]
    for pn in pnames:
      fn = "%s/%s" % (flag_outdir, pn)
      tojoin = [fn]
      tojoin.extend(infixes)
      tojoin.append("txt")
      fn = ".".join(tojoin)
      profiles[pn] = fn

    # Write to file
    for p, dest in profiles.items():
      ppo.write("%s > %s\n" % (p, dest))
    ppo.write("quit\n")
    ppo.close()

    if u.verbosity_level() > 1:
      u.verbose(0, "tempfile contents:")
      u.docmd("cat %s" % scriptf.name)

    # Execute
    pcmd = "%s %s %s %s" % (flag_pprof_path, ppopt, flag_binary,
                            " ".join(flag_infiles))
    docmdinout(pcmd, scriptf.name, outf.name)

    # Check to make sure the files turned up.
    if not flag_dryrun:
      for p, dest in profiles.items():
        if not os.path.exists(dest):
          u.error("error: %s profile '%s' not present "
                  "after pprof run" % (p, dest))


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options]

    options:
    -i X  input files are in X (list separated by ':')
    -o D  output dir is D
    -b B  binary path is B
    -p P  pprof path is P
    -m    generate heap profile variants
    -t T  tag output files with tag T
    -e    echo commands before executing
    -d    increase debug msg verbosity level
    -D    dryrun mode (echo commands but do not execute)

    Example usage:

    %s -b myprogram.exe -i f1.p:f2.p:f3.p -o outdir -t release

    """ % (me, me))

  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_echo, flag_dryrun, flag_infiles, flag_outdir, flag_tag
  global flag_binary, flag_pprof_path, flag_memvariants

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "dmeDi:o:t:p:b:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  if args:
    usage("unknown extra args: %s" % " ".join(args))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-D":
      u.verbose(0, "+++ dry run mode")
      flag_dryrun = True
      flag_echo = True
    elif opt == "-e":
      flag_echo = True
    elif opt == "-m":
      flag_memvariants = True
    elif opt == "-i":
      infiles = arg.split(":")
      u.verbose(1, "%d input files" % len(infiles))
      for inf in infiles:
        if not os.path.exists(inf):
          usage("unable to access -i input file %s" % inf)
        flag_infiles.append(inf)
    elif opt == "-o":
      if not os.path.exists(arg):
        usage("unable to access -o argument %s" % arg)
      if not os.path.isdir(arg):
        usage("-o argument %s not a directory" % arg)
      flag_outdir = arg
    elif opt == "-p":
      if not os.path.exists(arg):
        usage("unable to access -p argument %s" % arg)
      flag_pprof_path = arg
    elif opt == "-t":
      flag_tag = arg
    elif opt == "-b":
      if not os.path.exists(arg):
        usage("unable to access -b argument %s" % arg)
      flag_binary = arg

  if not flag_infiles:
    usage("supply input files with -i")
  if not flag_outdir:
    usage("supply output dir with -o")
  if not flag_binary:
    usage("supply executable path with -b")


#......................................................................
#
# Main portion of script
#
parse_args()
u.setdeflanglocale()
perform()
exit(0)
