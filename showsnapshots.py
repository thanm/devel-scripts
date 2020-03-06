#!/usr/bin/python
"""Small helper script to dump out BTRFS subvolumes.

This script dumps out the BTRFS subvolumes and snapshots of those
subvolumes for volumes rooted in /ssd* on the current machine.
The info provided by the 'btrfs subvolume list' command is
not very human-friendly -- in particular it is hard to use
it to determine the parent volume or snapshot for a given snapshot
(which is the key item of interest).

"""

from collections import defaultdict
import getopt
import os
import re
import sys

import script_utils as u


# SSD roots to look at
ssdroot_list = []

# User passed -s flag (run repo status)
flag_terse_output = False

# User passed -z flag (run 'du -sh')
flag_showsize = False

# User passed -t flag (sort by modtime)
flag_sort_modtime = False

# Report non-volume root dirs
flag_report_nonvol = True

# Show only repo volumes
flag_only_repos = False

# Look only at current dir
flag_dot = False

# Holds size info from 'du'
volsizes = {}


def indlev(lev):
  for _ in range(0, lev):
    sys.stdout.write(" ")


def get_mtime(ssdroot, vol):
  """Get last modification time of snapshot/volume."""
  return os.stat("%s/%s" % (ssdroot, vol)).st_mtime


def printvol(v, voldict, il, ssdroot):
  """Display info for a given subvolume or snapshot."""
  if v not in voldict:
    return
  subdict = voldict[v]
  for sn in sorted(subdict.keys()):
    indlev(il+2)
    par = ""
    if flag_terse_output:
      par = "%s/%s -> " % (ssdroot, v)
    if flag_showsize:
      sv = "%s/%s" % (ssdroot, sn)
      if sv in volsizes:
        par = "%s " % volsizes[sv]
      else:
        u.verbose(1, "no size info for %s" % sv)
    print "snapshot %s%s/%s" % (par, ssdroot, sn)
    printvol(sn, voldict, il+2, ssdroot)


def examine_ssdroot(ssdroot):
  """Show subvolumes and snapshots in a specific root dir."""

  if not flag_terse_output:
    lines = u.docmdlines("df -h %s" % ssdroot)
    dfline = lines[1]
    dfline = re.sub(r"\s+", " ", dfline)
    print "............. %s ............." % dfline

  if flag_showsize:
    print "... gathering size info with 'du'"
    lines = u.docmdlines("du -h -d 1 %s" % ssdroot)
    print "... done"
    for line in lines:
      chunks = line.split()
      volsizes[chunks[1]] = chunks[0]

  # This maps uid to volume
  uid_vol = {}

  # This maps uid to 'pending deletion' flag. When a subvolume or snapshot
  # deletion is issued, it takes a while for the kernel to catch up... until
  # the delete is finalized the pending-delete volume will show as "DELETED".
  uid_pending_delete = {}

  # This maps volume to uid
  vol_uid = {}

  # This maps volume to mtime
  vol_mtime = {}

  # This maps volume to parent uid
  vol_puid = {}

  # Run the subvolume list command and collects its cryptic output
  lines = u.docmdlines("sudo btrfs subvolume list -qu %s" % ssdroot)

  # Pattern we're looking for in the btrfs output
  matcher = re.compile(r"^ID \d+ gen \d+ top level \d+ "
                       r"parent_uuid\s+(\S+)\s+uuid (\S+) path (\S+)\s*")

  # Run through all of the lines:
  for line in lines:
    if not line:
      continue
    # Match
    m = matcher.match(line)
    if m is None:
      u.error("line did not match: %s" % line)
    puid = m.group(1)
    uid = m.group(2)
    vol = m.group(3)
    u.verbose(2, "matched puid=%s uid=%s vol=%s" % (puid, uid, vol))
    if flag_sort_modtime:
      vol_mtime[vol] = get_mtime(ssdroot, vol)
    if vol == "DELETED":
      uid_pending_delete[uid] = 1
      continue
    if vol in vol_uid:
      u.error("internal error: unexpected repeated vol " + vol)
    if uid in uid_vol:
      u.error("internal error: unexpected repeated uid " + uid)
    vol_uid[vol] = uid
    uid_vol[uid] = vol
    if puid != "-":
      vol_puid[vol] = puid

  # Key is vol, value is dictionary of subvolumes
  voldict = defaultdict(lambda: defaultdict(int))

  # Evaluate parent subvolume relationships
  for sv, puid in vol_puid.items():
    if puid not in uid_vol:
      # Orphan snapshot
      u.warning("%s/%s appears to be orphaned; "
                "treating as subvolume" % (ssdroot, sv))
      del vol_puid[sv]
    else:
      pv = uid_vol[puid]
      voldict[pv][sv] = 1

  # For -t output, have parent vol modtime inherit from children
  if flag_sort_modtime:
    for pv, svdict in voldict.iteritems():
      for cv in svdict:
        pvm = vol_mtime[pv]
        cvm = vol_mtime[cv]
        if cvm > pvm:
          u.verbose(2, "bumping par %s mtime from %s "
                    "to %s based on child %s" % (pv, pvm, cvm, cv))
          vol_mtime[pv] = cvm

  vols = sorted(vol_uid.keys())
  if flag_dot:
    # For flag_dot, we're only interested in snapshots and volumes
    # related to the current directory. Start by locating the snap
    # or volume that we're in at the moment.
    vols = []
    here = os.getcwd()
    path_components = here.split("/")
    curvol = "%s" % path_components[2]
    u.verbose(2, "flag_dot: evaluating curvol=%s" % curvol)
    if curvol in vol_uid:
      uid = vol_uid[curvol]
      u.verbose(2, "flag_dot: curvol=%s uid=%s" % (curvol, uid))
      # Find parent volume if applicable.
      if curvol in vol_puid:
        uid = vol_puid[curvol]
        curvol = uid_vol[uid]
        u.verbose(2, "flag_dot: parent curvol=%s uid=%s" % (curvol, uid))
      # Now add vol itself and all children to tups list.
      vols.append(curvol)
      if curvol in voldict:
        sv = voldict[curvol]
        for v in sv:
          vols.append(v)
      u.verbose(2, "flag_dot: final vols: %s" % vols)

  # Sort order
  tups = []
  for v in vols:
    mtime = 0
    if flag_sort_modtime:
      mtime = vol_mtime[v]
    tup = (mtime, v)
    tups.append(tup)

  # Output for regular volumes
  sltups = sorted(tups)
  for t in sltups:
    v = t[1]
    if v not in vol_puid:
      subvol = os.path.join(ssdroot, v)
      if flag_only_repos:
        if not os.path.exists(os.path.join(subvol, ".repo")):
          continue
      vsize = ""
      if flag_showsize:
        sv = "%s/%s" % (ssdroot, v)
        if sv in volsizes:
          vsize = "%s " % volsizes[sv]
        else:
          u.verbose(1, "no size info for %s" % sv)
      print "subvolume %s%s/%s" % (vsize, ssdroot, v)
      printvol(v, voldict, 2, ssdroot)

  # Show pending deletions
  if not flag_terse_output:
    dsortedkeys = sorted(uid_pending_delete.keys())
    for v in dsortedkeys:
      print "[pending deletion: subvolume uid %s]" % v

  # Show things that are not snapshots/volumes
  nonvolumes = []
  if flag_report_nonvol:
    for filename in os.listdir(ssdroot):
      if filename not in vol_uid:
        nonvolumes.append(filename)
    if not flag_terse_output and nonvolumes:
      print "++ non-volumes: %s" % " ".join(nonvolumes)


def find_ssdroots():
  """Return a list of all BTRFS filesystems mounted."""
  btrfsmounts = u.docmdlines("mount -l -t btrfs")
  matcher = re.compile(r"^\S+ on (\S+) ")
  rootlist = []
  for line in btrfsmounts:
    m = matcher.match(line)
    if m is None:
      u.warning("warning: pattern match failed for "
                "output of mount -l: %s" % line)
    else:
      rootlist.append(m.group(1))
  if not rootlist:
    u.error("unable to locate any BTRFS mounts "
            "from 'mount -l -t btrfs' -- aborting")
  return rootlist


def check_btrfs(rdir):
  """Check to make sure that 'rdir' is a BTRFS filesystem."""

  outlines = u.docmdlines("stat -f --printf=%%T %s" % rdir)
  if not outlines:
    u.error("internal error-- could not determine FS type for dir %s" % rdir)
  if outlines[0] != "btrfs":
    u.error("FS type for %s is %s, not btrfs (can't "
            "proceed)" % (rdir, outlines[0]))


def find_ssdroot_from_args(dirs):
  """Find root BTRFS mount point for specified args."""
  rootlist = []
  for rdir in dirs:
    absdir = os.path.abspath(rdir)
    if not os.path.exists(absdir):
      u.error("unable to access specified location %s "
              "(abspath %s)" % (rdir, absdir))
    path_components = absdir.split("/")
    root = "/%s" % path_components[1]
    check_btrfs(root)
    rootlist.append(root)
  return rootlist


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options] [dir]

    options:
    -d    increase debug msg verbosity level
    -r    examine only subvolumes with repos
    -s    run 'repo status' in each repo encountered
    -z    run 'du -sh' on each snapshot/volume to show size
    -n    do not report on non-volume/non-snapshot root dirs
    -m    emit output in a lispy, script-readable format
    -t    list volumes/snapshots from least-recently to most-recently
          used (based on leaf snapshot)

    Displays BTRFS subvolumes/snapshots for any BTRFS filesystems
    currently mounted.  If optional "dir" arg is supplied, display
    info only for filesystem containing that dir. If the dir is
    ".", then show only snapshots and volumes related to the current
    dir.

    """ % os.path.basename(sys.argv[0])
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global ssdroot_list, flag_report_nonvol, flag_sort_modtime
  global flag_only_repos, flag_terse_output, flag_showsize, flag_dot

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "dnmrstz")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, _ in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-r":
      flag_only_repos = True
    elif opt == "-m":
      flag_terse_output = True
    elif opt == "-z":
      flag_showsize = True
    elif opt == "-t":
      flag_sort_modtime = True
    elif opt == "-n":
      flag_report_nonvol = False

  if not args:
    ssdroot_list = find_ssdroots()
  else:
    if len(args) == 1 and args[0] == ".":
      flag_dot = True
    ssdroot_list = find_ssdroot_from_args(args)
  if flag_showsize and flag_terse_output:
    usage("-m and -z options are incompatible")


# Main portion of script
u.setdeflanglocale()
parse_args()
for sr in ssdroot_list:
  examine_ssdroot(sr)

exit(0)
