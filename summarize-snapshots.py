#!/usr/bin/python
"""Summarize repo/git activity in snapshots/volumes.

This script walks the SSD roots on the machine and summarizes
repo/git status as well as size.  WIP.

"""

from collections import defaultdict
import getopt
import multiprocessing
import os
import re
import sys
import tempfile

import script_utils as u


# Output file instead of stdout
flag_outfile = None

# Email report to user
flag_email_dest = None

# Dry run
flag_dryrun = False

# Output file handle
outf = None

# Debugging
flag_shortrun = False

# User
whoami = None

# Temp file if needed
tmpfile = None


def indlev(lev):
  """Indent to specified level."""
  for _ in range(0, lev):
    outf.write(" ")


def emitlines(lines, lev):
  """Emit array of lines, indented."""
  for line in lines:
    indlev(lev)
    outf.write("%s\n" % line.rstrip())


def emit(v, resdict, voldict, lev):
  """Emit results for volume v and children."""
  u.verbose(1, "emit for volsnap %s" % v)
  apair = resdict[v]

  # Disk space summary
  dutf = apair[0]
  amt = "<unknown>"
  with open(dutf, "r") as rdf:
    lines = rdf.readlines()
    amtl = lines[0].strip()
    a = amtl.split()
    amt = a[0]
  os.unlink(dutf)
  indlev(lev)
  outf.write("%s: %s\n" % (v, amt))

  # Repo status summary
  rptf = apair[1]
  if rptf:
    with open(rptf, "r") as rrf:
      lines = rrf.readlines()
      indlev(lev+2)
      outf.write("----------------------------------------\n")
      emitlines(lines, lev+2)
      indlev(lev+2)
      outf.write("----------------------------------------\n")
    os.unlink(rptf)

  # Now any subvolumes
  subdict = voldict[v]
  for sv in sorted(subdict.keys()):
    u.verbose(1, "considering sv %s" % sv)
    if sv in resdict:
      emit(sv, resdict, voldict, lev+4)


def process_volsnap(v):
  """Examine a given subvolume or snapshot."""
  me = whoami
  sv = re.sub("/", "_", v)
  tf1 = "/tmp/ssnap-%s-%s-du.txt" % (me, sv)
  os.chdir(v)
  u.verbose(1, "collecting disk for %s into %s" % (v, tf1))
  u.docmdout("du -sh", tf1)
  tf2 = None
  rp = os.path.join(v, ".repo")
  if os.path.exists(rp):
    tf2 = "/tmp/ssnap-%s-%s-rpstat.txt" % (me, sv)
    u.verbose(1, "collecting rpstat for %s into %s" % (v, tf2))
    u.docmdout("repo status", tf2)
  return (tf1, tf2)


def collect_subvolumes_and_snapshots(volumes, snapshots, voldict):
  """Collect info on volumes and snapshots."""
  lines = u.docmdlines("showsnapshots.py -m")
  volm = re.compile(r"^subvolume (\S+)\s*$")
  snapm = re.compile(r"^\s+snapshot (\S+)\s+\->\s+(\S+)\s*$")
  for line in lines:
    m1 = volm.match(line)
    if m1:
      pv = m1.group(1)
      volumes[pv] = 1
      continue
    m2 = snapm.match(line)
    if m2:
      pv = m2.group(1)
      sv = m2.group(2)
      snapshots[sv] = 1
      voldict[pv][sv] = 1
      continue
    u.warning("unmatchable line from %s "
              "output: %s" % ("showsnapshots -m", line))


def perform():
  """Main driver routine."""

  # Volumes
  volumes = {}

  # Snapshots
  snapshots = {}

  # Key is vol, value is dictionary of subvolumes
  voldict = defaultdict(lambda: defaultdict(int))

  # Multiprocessing pool
  nworkers = 8
  pool = multiprocessing.Pool(processes=nworkers)

  # Get info on volumes
  collect_subvolumes_and_snapshots(volumes, snapshots, voldict)

  # Kick off job for each volume, then snapshot
  results = []
  snapvols = []
  for v in volumes:
    u.verbose(1, "enqueue job for vol %s" % v)
    r = pool.apply_async(process_volsnap, [v])
    results.append(r)
    snapvols.append(v)
    if flag_shortrun:
      break
  for sv in snapshots:
    u.verbose(1, "enqueue job for snap %s" % sv)
    r = pool.apply_async(process_volsnap, [sv])
    results.append(r)
    snapvols.append(sv)
    if flag_shortrun:
      break

  # Collect results
  resdict = {}
  nr = len(results)
  for idx in range(0, nr):
    r = results[idx]
    v = snapvols[idx]
    u.verbose(1, "waiting on result %d %s" % (idx, v))
    pair = r.get(timeout=200)
    resdict[v] = pair

  # Emit results
  for v in volumes:
    if v in resdict:
      emit(v, resdict, voldict, 0)
  outf.close()

  if flag_email_dest:
    cmd = ("sendgmr --to=%s --body_file=%s "
           "--subject='repo status "
           "summary'" % (whoami, flag_outfile))
    u.verbose(1, "email cmd is: %s" % cmd)
    u.docmd(cmd)


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options] [dir]

    options:
    -d    increase debug msg verbosity level
    -o F  emit output to file F
    -m U  email output to user U
    -S    debugging: short run (single subvolume + snapshot)

    Summarizes disk space usage and repo status for repos located
    in SSD roots.

    """ % os.path.basename(sys.argv[0])
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_outfile, flag_email_dest, flag_shortrun, outf, whoami
  global tmpfile

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "Sdo:m:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))
  if args:
    usage("unknown extra arguments")

  outf = sys.stdout
  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-S":
      flag_shortrun = True
    elif opt == "-m":
      if flag_email_dest:
        u.usage("specify at most one email dest")
      flag_email_dest = arg
    elif opt == "-o":
      if flag_outfile:
        u.usage("specify at most one output file")
      flag_outfile = arg

  if flag_email_dest and not flag_outfile:
    tmpfile = tempfile.NamedTemporaryFile(mode="w", delete=True)
    flag_outfile = tmpfile.name
  if flag_outfile:
    try:
      outf = open(flag_outfile, "wb")
    except IOError as e:
      u.error("unable to open output file %s: "
              "%s" % (flag_outfile, e.strerror))
  lines = u.docmdlines("whoami")
  whoami = lines[0].strip()


# Main portion of script
u.setdeflanglocale()
parse_args()
perform()
exit(0)
