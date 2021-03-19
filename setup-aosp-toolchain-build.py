#!/usr/bin/python3
"""Script to create AOSP toolchain development work area.

Creates symbolic links in /tmp and runs setup scripts.

"""

import getopt
import os
import sys

import script_utils as u


# Path to working AOSP or NDK repo
flag_ndk_repo = None

# Path to working toolchain repo (optional)
flag_toolchain_repo = None

# Echo command before executing
flag_echo = True

# Dry run mode
flag_dryrun = False

# Root of work area
flag_workdir = "/tmp"

# Default gcc version
flag_gcc_version = None

# Create platform links
flag_create_platform_links = False

# Work linkst
aosp_link = None
aosp_toolchain_link = None


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


def check_dir(adir):
  """Check that a directory exists."""
  if not os.path.exists(adir):
    return False
  if not os.path.isdir(adir):
    return False
  return True


def check_repo(arepo):
  """Check that arepo is a repo client."""
  if not check_dir(arepo):
    u.error("unable to access repo dir %s" % arepo)
  if not check_dir("%s/.repo" % arepo):
    u.error("repo client %s does not contain .repo dir")


def check_inputs():
  """Check that setup and inputs are legal."""
  global flag_toolchain_repo
  check_repo(flag_ndk_repo)
  if flag_toolchain_repo:
    check_repo(flag_toolchain_repo)
  else:
    flag_toolchain_repo = "%s/toolchain" % flag_ndk_repo
  if not check_dir(flag_workdir):
    u.error("can't access workdir %s" % flag_workdir)


def create_or_check_link(src, dst):
  """Create or check a symbolic link."""
  if not os.path.exists(dst):
    u.verbose(0, "... creating link %s -> %s" % (dst, src))
    os.symlink(src, dst)
  else:
    u.verbose(0, "... verifying link %s -> %s" % (dst, src))
    if not os.path.islink(dst):
      u.error("can't proceed: %s exists but is not a link" % dst)
    ltarget = os.readlink(dst)
    if ltarget != src:
      u.error("can't proceed: %s exists but points to %s "

              "instead of %s" % (dst, ltarget, src))


def perform():
  """Perform setups."""
  global aosp_link, aosp_toolchain_link
  # Create or check symbolic links
  aosp_link = "%s/AOSP" % flag_workdir
  create_or_check_link(flag_ndk_repo, aosp_link)
  aosp_toolchain_link = "%s/AOSP-toolchain" % flag_workdir
  create_or_check_link(flag_toolchain_repo, aosp_toolchain_link)
  # Environment variable settings
  aosp_ndk = "%s/ndk" % aosp_link
  os.environ["NDK"] = aosp_ndk
  os.environ["ANDROID_BUILD_TOP"] = flag_ndk_repo
  # Change dir
  arches = "arm,x86,mips,arm64,x86_64,mips64"
  dochdir(aosp_ndk)
  docmd("./build/tools/dev-cleanup.sh")
  gccv = ""
  if flag_gcc_version:
    gccv = "--gcc-version=%s" % flag_gcc_version
  if flag_create_platform_links:
    docmd("./build/tools/gen-platforms.sh --minimal "
          "--dst-dir=%s --ndk-dir=%s %s "
          "--arch=%s" % (aosp_ndk, aosp_ndk, gccv, arches))
  else:
    u.verbose(1, "skipping platform link creation step")


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options]

    options:
    -d    increase debug msg verbosity level
    -n X  AOSP or NDK repo path is X
    -t Y  toolchain repo path is (use toolchain subdir of NDK if present)
    -w Z  work dir is Z (def: /tmp)
    -P    set up platform links in NDK dir (not required since mid-2015)
    -q    quiet mode (do not echo commands before executing)
    -D    dryrun mode (echo commands but do not execute)
    -g V  set up build for specific gcc version V (ex: 5.2)

    Example 1: set up build with toolchain repo + AOSP dir

      %s -t /ssd/toolchain -n /ssd/aosp_hammerhead-userdebug

    Example 2: set up build with just NDK repo

      %s -n /ssd/ndk

    """ % (me, me, me))
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_ndk_repo, flag_toolchain_repo, flag_create_platform_links
  global flag_echo, flag_dryrun, flag_workdir, flag_gcc_version

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "dn:t:w:g:qDP")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-q":
      flag_echo = False
    elif opt == "-D":
      flag_dryrun = True
    elif opt == "-P":
      flag_create_platform_links = True
    elif opt == "-n":
      flag_ndk_repo = arg
    elif opt == "-t":
      flag_toolchain_repo = arg
    elif opt == "-w":
      flag_workdir = arg
    elif opt == "-g":
      flag_gcc_version = arg

  if args:
    usage("unknown extra args")
  if not flag_ndk_repo:
    usage("specify ndk repo path -n")


#
#......................................................................
#
# Main portion of script
#
parse_args()
u.setdeflanglocale()
check_inputs()
perform()
exit(0)
