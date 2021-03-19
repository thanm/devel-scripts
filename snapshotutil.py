#!/usr/bin/python3
"""Script to manage creation/deletion of BTRFS subvolumes/snapshots.

This script helps facilitate the creation of BTRFS subvolumes and
snapshots, with an end towards enabling better SSD utilization for
Android development. Android "repo" clients can be very large: 60-70GB
for a fully built AOSP client, and 150-170GB for a fully built
internal-tree client.  Most of this space is taken up by .git data
(compiled output/object files are only about 30GB), which makes such
clients ideal candidates for BTRFS (a filesystem that supports snapshots
with "copy-on-write" semantics).

The intended usage model for the script is as follows:

 1. create a BTRFS subvolume 'vol'
 2. populate an Android client within 'vol' using "repo init" / "repo sync"
 3. create a BTRFS snapshot of 'vol' named 'work', then configure
    and build within 'work'
 4. repeat step 3 for different device configurations

After the subvolume is created, each snapshot will only have an
incremental cost of ~30GB (size of derived "out" dir), meaning that
one can fit 2-4 clients on a given 256GB SSD as opposed to only a
single client.

All of the above can be done using raw 'btrfs' commands, however the
process of doing so is tricky and error-prone. The role of this script
is to provide an additional layer that helps avoid problematic usages
(ex: creating a snapshot within a snapshot, etc). Available
subcommands:

  mkvol   --   create a new subvolume
  mksnap  --   create a new snapshot
  rmvol   --   remove subvolume
  rmsnap  --   remove snapshot

Note: because commands such as "btrfs subvolume create" have to be run
via "sudo", this script can really only be run interactively (since
'sudo' will prompt for input). The script also helps retroactively
change the ownership/permissions to correspond to the script
invoker in cases where new snapshots/volumes are created.

The assumptions made by this script:

 1. the current dir at script invocation is somewhere in the BTRFS
    SSD on which we want to operate
 2. all snapshots/subvolumes will be direct descendents of the root
    SSD (e.g. we're creating '/ssd/newvolume' and not '/ssd/x/y/newvolume'

"""

import getopt
import os
import re
import sys

import script_utils as u


# Subcommand
flag_subcommand = None

# Subcommand arguments
flag_subcommand_args = []

# Homedir, use
flag_homedir = os.getenv("HOME")


# Legal subcommands, with their required number of arguments
possible_subcommands = {
    "mkvol": 1,
    "mksnap": 2,
    "rmvol": 1,
    "rmsnap": 1
    }


def repair(newvolume):
  """Repair ownership/permissions for new snapshot/subvolume."""
  u.docmd("sudo chown --reference=%s %s" % (flag_homedir, newvolume))
  u.docmd("sudo chgrp --reference=%s %s" % (flag_homedir, newvolume))
  u.docmd("chmod 0750 %s" % newvolume)


def normalize(ssdroot, volsnapname):
  """Remove initial /ssdroot, check for bad name."""
  sr = ssdroot + "/"
  vsn = volsnapname
  if volsnapname.startswith(sr):
    srl = len(sr)
    vsn = volsnapname[srl:]
  if vsn.find("/") != -1:
    u.error("illegal volume or snapshot name %s "
            "(must refer to top level dir)" % volsnapname)
  return vsn


def mkvol_subcommand(volname):
  """Create a new btrfs subvolume."""

  # Determine /ssd root
  ssdroot = u.determine_btrfs_ssdroot(os.getcwd())
  u.verbose(1, "ssdroot=%s" % ssdroot)

  # Normalize snap name
  volname = normalize(ssdroot, volname)

  # Check to make sure the new volume doesn't already exist
  newvolume = "%s/%s" % (ssdroot, volname)
  if os.path.exists(newvolume):
    u.error("path %s already exists -- can't create" % newvolume)

  # Here goes
  u.docmd("sudo btrfs subvolume create %s" % newvolume)

  # Repair ownership/permissions
  repair(newvolume)

  sys.stderr.write("... new subvolume %s created\n" % newvolume)


def mksnap_subcommand(volname, snapname):
  """Snapshot an existing BTRFS subvolume or snapshot."""

  # Determine /ssd root
  ssdroot = u.determine_btrfs_ssdroot(os.getcwd())
  u.verbose(1, "ssdroot=%s" % ssdroot)

  # Normalize snap name, volume name
  volname = normalize(ssdroot, volname)
  snapname = normalize(ssdroot, snapname)

  # Existing volume should exist
  oldvolume = "%s/%s" % (ssdroot, volname)
  if not os.path.exists(oldvolume):
    u.error("unable to locate existing subvolume %s" % oldvolume)

  # Check to make sure the new snapshot doesn't already exist
  newsnap = "%s/%s" % (ssdroot, snapname)
  if os.path.exists(newsnap):
    u.error("path %s already exists -- can't create" % newsnap)

  # Here goes
  u.docmd("sudo btrfs subvolume snapshot %s %s" % (oldvolume, newsnap))

  # Repair ownership/permissions
  repair(newsnap)

  sys.stderr.write("... new snapshot %s created\n" % newsnap)


def rmvolsnap(volsnapname, which):
  """Remove an existing btrfs snapshot or subvolume."""

  # Determine /ssd root
  ssdroot = u.determine_btrfs_ssdroot(os.getcwd())
  u.verbose(1, "ssdroot=%s" % ssdroot)

  # Normalize snap name
  volsnapname = normalize(ssdroot, volsnapname)

  # Check for existence
  oldvolsnap = "%s/%s" % (ssdroot, volsnapname)
  if not os.path.exists(oldvolsnap):
    u.error("unable to locate existing %s %s" % (which, oldvolsnap))

  # Determine whether there is a parent uuid
  isvol = -1
  showlines = u.docmdlines("sudo btrfs subvolume show %s" % oldvolsnap)
  if not showlines:
    u.error("unable to get subvolume info for %s" % oldvolsnap)
  matcher = re.compile(r"^\s*Parent uuid\:\s+(\S+).*$")
  for line in showlines:
    m = matcher.match(line)
    if m:
      puid = m.group(1)
      if puid == "-":
        isvol = 1
      else:
        isvol = 0

  u.verbose(2, "isvol=%d for %s" % (isvol, oldvolsnap))

  if isvol == -1:
    u.warning("unable to determine snapshot/subvolume status for %s" %
              oldvolsnap)
  elif isvol == 0:
    if which == "volume":
      u.warning("%s appears to be snapshot, not subvolume" % oldvolsnap)
  else:
    if which == "snapshot":
      u.warning("%s appears to be subvolume, not snapshot" % oldvolsnap)

  # Here goes
  rc = u.docmdnf("sudo btrfs subvolume delete %s" % oldvolsnap)
  if rc != 0:
    # Couldn't delete the subvolume. Suggest running lsof
    sys.stderr.write("** deletion failed -- trying to determine open file:\n")
    sys.stderr.write("  lsof +D %s\n"% oldvolsnap)
    u.docmdnf("lsof +D %s\n" % oldvolsnap)
    exit(1)

  sys.stderr.write("... %s %s deleted\n" % (which, oldvolsnap))


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options] <subcommand> ...args...

    options:
    -d    increase debug msg verbosity level

    subcommands:

      mkvol V      creates new subvolume V
      rmvol V      remove existing subvolume V
      mksnap E S   create new snapshot "S" from existing volume/snapshot E
      rmsnap  S    remove snapshot S

    """ % os.path.basename(sys.argv[0]))
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""

  global flag_subcommand, flag_subcommand_args

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "d")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, _ in optlist:
    if opt == "-d":
      u.increment_verbosity()

  if not args:
    usage("specify subcommand")

  flag_subcommand = args[0]
  if flag_subcommand not in possible_subcommands:
    usage("unknown subcommand %s" % flag_subcommand)
  nargs = len(args) - 1
  if nargs < 1:
    usage("no subcommand arguments specified")
  flag_subcommand_args = args[1:]
  req_args = possible_subcommands[flag_subcommand]
  if nargs != req_args:
    usage("subcommand %s requires %d args, %d supplied" %
          (flag_subcommand, req_args, nargs))

  if not flag_homedir:
    usage("environment variable HOME not set")


#
#......................................................................
#
# Main portion of script
#
parse_args()
u.setdeflanglocale()
if flag_subcommand == "mksnap":
  mksnap_subcommand(flag_subcommand_args[0],
                    flag_subcommand_args[1])
elif flag_subcommand == "mkvol":
  mkvol_subcommand(flag_subcommand_args[0])
elif flag_subcommand == "rmvol":
  rmvolsnap(flag_subcommand_args[0], "volume")
elif flag_subcommand == "rmsnap":
  rmvolsnap(flag_subcommand_args[0], "snapshot")
else:
  u.error("internal error: bad subcommand %s" % flag_subcommand)

exit(0)
