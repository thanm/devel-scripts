#!/usr/bin/python3
"""Perform a previously configured AOSP toolchain build.

This script kicks off a series of builds of the toolchain gcc compiler
for Android. It relies on previously established symbolic links set
up by hand or by "setup-aosp-toolchain-build.py".

"""

import getopt
import importlib
import multiprocessing
import os
import sys

import script_utils as u

# Path to working AOSP or NDK repo
flag_aosp_link = "/tmp/AOSP"

# Path to working AOSP or NDK repo
flag_toolchain_link = None

# Echo command before executing
flag_echo = True

# Dry run mode
flag_dryrun = False

# gcc version
flag_gcc_version = "4.9"

# isl version
flag_isl_version = None

# arches to build
flag_arches = None

# build different arches in parallel
flag_parallel = False

# Place where NDK build artifacts will be written
flag_ndk_builddir = "/ssd2/ndkbuild"

# Legal build arches
legal_arches = {"aarch64-linux-android": 1,
                "arm-linux-androideabi": 1,
                "x86": 1, "mipsel-linux-android": 1,
                "x86_64": 1, "mips64el-linux-android": 1}

# Host option to pass to build-gcc.sh
flag_hostopt = ""

# Build a debuggable gcc
flag_build_debuggable = False

# Links in /tmp
aosp_ndk_link = None
aosp_toolchain_link = None


def docmd(cmd):
  """Execute a command."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmd(cmd)


def docmdnf(cmd):
  """Execute a command allowing for failure."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return 0
  return u.docmdnf(cmd)


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


def set_evar(var, val):
  """Set an environment variable prior to script execution."""
  os.environ[var] = val
  u.verbose(0, "Setting %s to: %s" % (var, val))


def perform():
  """Perform setups."""
  rc = 0

  # Import correct module and collect sysroot_path method
  loc = "%s/build/lib" % aosp_ndk_link
  u.verbose(1, "importing %s/build_support.py" % loc)
  sys.path.append(loc)
  mod = importlib.import_module("build_support")
  sysroot_method = getattr(mod, "sysroot_path")
  if not sysroot_method:
    u.error("internal error: can't find sysroot_path "
            "method in %s/build_support.py" % loc)

  # Environment variable settings
  set_evar("NDK", aosp_ndk_link)
  set_evar("ANDROID_BUILD_TOP", flag_aosp_link)
  set_evar("ANDROID_NDK_ROOT", aosp_ndk_link)
  set_evar("NDK_BUILDTOOLS_PATH", "%s/build/tools" % aosp_ndk_link)
  set_evar("TMPDIR", "%s/tmpdir" % flag_ndk_builddir)

  # The script build-gcc.sh inspects the value of GCC_VERSION
  if flag_gcc_version:
    set_evar("GCC_VERSION", flag_gcc_version)

  tmpdir = "%s/tmpdir" % flag_ndk_builddir
  ndk_temp = "%s/build" % flag_ndk_builddir
  prebuilt_path = "%s/prebuilts" % flag_ndk_builddir
  islv = ""
  if flag_isl_version:
    islv = "--isl-version=%s" % flag_isl_version

  sixtyfouropt = "--try-64"
  winopt = ""
  if flag_hostopt == "windows":
    sixtyfouropt = ""
    winopt = "--mingw"
  elif flag_hostopt == "windows64":
    winopt = "--mingw"

  dbgopt = ""
  if flag_build_debuggable:
    dbgopt = "--build-debuggable=yes"

  # Change dir
  dochdir(aosp_ndk_link)

  # Create build dir if needed
  docmd("mkdir -p %s" % flag_ndk_builddir)

  # Clean
  u.verbose(0, "... cleaning temp dirs")
  docmd("rm -rf %s %s %s" % (tmpdir, ndk_temp, prebuilt_path))
  docmd("mkdir %s %s %s" % (tmpdir, ndk_temp, prebuilt_path))

  pool = None
  if flag_parallel:
    nworkers = multiprocessing.cpu_count()-1
    pool = multiprocessing.Pool(processes=nworkers)

  # Build
  results = []
  for arch in flag_arches:
    sysroot_setting = sysroot_method(arch)
    cmd = ("%s/gcc/build-gcc.sh %s "
           "%s %s --package-dir=%s "
           "--obscure-prefix=no "
           "--sysroot=%s "
           "--build-out=%s %s %s %s %s-%s" %
           (aosp_toolchain_link, islv,
            aosp_toolchain_link, aosp_ndk_link, prebuilt_path,
            sysroot_setting, ndk_temp,
            sixtyfouropt, winopt, dbgopt,
            arch, flag_gcc_version))
    u.verbose(1, "build cmd is: %s" % cmd)
    if flag_parallel:
      r = pool.apply_async(docmd, [cmd])
      results.append(r)
    else:
      res = docmdnf(cmd)
      if res != 0:
        rc = 1

  # Reap results for parallel execution
  nr = len(results)
  for idx in range(0, nr):
    r = results[idx]
    u.verbose(1, "waiting on result %d" % idx)
    res = r.get(timeout=600)
    if res != 0:
      rc = 1

  return rc


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  la = " ".join(list(legal_arches.keys()))
  print("""\
    usage:  %s [options]

    options:
    -d    increase debug msg verbosity level
    -b X  set root build dir to X (def: /ssd/ndkbuild)
    -n X  AOSP build link is X (def: /tmp/AOSP)
    -t Y  AOSP toolchain src link is Y (def: /tmp/AOSP/toolchain)
    -q    quiet mode (do not echo commands before executing)
    -D    dryrun mode (echo commands but do not execute)
    -g Q  build for gcc version Q (def: 4.9)
    -a A  build target arch A (legal arches: %s)
          [may be specified multiple times]
    -w    build windows 32-bit toolchain
    -W    build windows 64-bit toolchain
    -C    build a debuggable copy of GCC
    -p    build different toolchains in parallel (experimental)

    Example 1: set up build with toolchain repo + AOSP dir

      %s -t /tmp/AOSP-toolchain -n /tmp/AOSP/ndk

    Example 2: set up build with just NDK repo, only aarch64 target

      %s -n /tmp/AOSP -a aarch64-linux-android

    Example 3: build gcc 5.2 with isl version 0.14 with just NDK repo

      %s -n /tmp/AOSP -g 5.2 -i 0.14

    """ % (me, la, me, me, me))
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_aosp_link, flag_toolchain_link
  global flag_echo, flag_dryrun, flag_ndk_builddir
  global flag_gcc_version, flag_isl_version, flag_arches
  global aosp_ndk_link, aosp_toolchain_link, flag_hostopt
  global flag_build_debuggable, flag_parallel

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "da:b:n:t:g:i:qDwCW")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  flag_arches = list(legal_arches.keys())
  specific_arches = {}
  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-q":
      flag_echo = False
    elif opt == "-D":
      flag_dryrun = True
    elif opt == "-C":
      flag_build_debuggable = True
    elif opt == "-n":
      flag_aosp_link = arg
    elif opt == "-p":
      flag_parallel = True
    elif opt == "-t":
      flag_toolchain_link = arg
    elif opt == "-b":
      flag_ndk_builddir = arg
    elif opt == "-g":
      flag_gcc_version = arg
    elif opt == "-i":
      flag_isl_version = arg
    elif opt == "-w":
      flag_hostopt = "windows"
    elif opt == "-W":
      flag_hostopt = "windows64"
    elif opt == "-a":
      if arg not in legal_arches:
        usage("specified arch %s not part of legal list" % arg)
      specific_arches[arg] = 1
  if specific_arches:
    flag_arches = sorted(specific_arches.keys())

  if args:
    usage("unknown extra args")
  aosp_ndk_link = "%s/ndk" % flag_aosp_link
  if flag_toolchain_link:
    aosp_toolchain_link = flag_toolchain_link
  else:
    aosp_toolchain_link = "%s/toolchain" % flag_aosp_link
  if not os.path.exists(aosp_ndk_link):
    usage("unable to access %s" % aosp_ndk_link)
  if not os.path.exists(aosp_toolchain_link):
    usage("unable to access %s" % aosp_toolchain_link)


#
#......................................................................
#
# Main portion of script
#
parse_args()
u.setdeflanglocale()
erc = perform()
if erc != 0:
  print("*** BUILD FAILED")
exit(erc)
