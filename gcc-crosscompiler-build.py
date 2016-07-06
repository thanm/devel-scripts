#!/usr/bin/python
"""Configure and/or build a GCC cross compiler.

Utilities for configuring and building a GCC cross compiler.
Assumption here is that "." (the directory we're invoked from)
contains the top-level download of gcc (either from a tar file or from
svn/git). The script will populate this directory with the necessary
pieces (e.g. binutils, gmp, etc), invoke configure with the proper
options, and then run the build steps.

"""

import getopt
import os
import re
import sys

import script_utils as u


# Echo command before executing
flag_echo = True

# Dry run mode
flag_dryrun = False

# Show command output (ex: make)
flag_show_output = False

# target architecture to build (ex: aarch64-linux-android)
flag_target_arch = None

# paralellism degree
flag_parfactor = "-j40"

# do only gcc build
flag_do_only_gcc_build = False

# languages to configure
flag_langs = "c,c++"

# legal additional languages
legal_extralangs = {"go": 1}

# whether to pass --disable-multilib
flag_use_multilib = ""

# whether to pass --disable-bootstrap
flag_use_bootstrap = "--disable-bootstrap"

# Legal build arches
legal_arches = {"aarch64-linux-android": "arm64",
                "arm-linux-androideabi": "arm",
                "x86": "x86",
                "mipsel-linux-android": "mipsel",
                "x86_64-linux-gnu": "x86_64",
                "x86_64": "x86_64",
                "x86_64-linux-android": "x86_64",
                "mips64el-linux-android": "mips64el"}

# name of subdir containing gcc (inferred)
flag_gcc_subdir = None

# gcc version (inferred)
gcc_version = None

# build debuggable gcc
flag_debug_gcc = False

# Android sysroot needed
flag_need_android_sysroot = False

# Android ndk dir
flag_ndk_dir = None

# Sysroot
sysroot = None

# here
here = os.getcwd()

# cross tools prefix
cross_prefix = os.path.join(here, "cross")

# gcc build dir
gcc_build_dir = "build-gcc"

# glibc build dir
glibc_build_dir = "build-glibc"

# binutils git remote (if we're using trunk)
binutils_git = "git://sourceware.org/git/binutils-gdb.git"

# binutils bin dir
binutils_build_dir = "build-binutils"

# binutils version. If unset, use trunk
binutils_version = None

# binutils subdir name
binutils_subdir = None

# glibc version
glibc_version = "2.20"

# kernel version
kernel_version = "linux-3.17.2"


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
  if flag_show_output:
    u.docmd(cmd)
  else:
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


def locate_gcc_subdir():
  """Find the gcc subdir in this dir."""
  global flag_gcc_subdir, gcc_version
  if not flag_gcc_subdir:
    matcher = re.compile(r"^gcc-.+$")
    found = None
    subgcc = None
    for filename in os.listdir("."):
      m = matcher.match(filename)
      if not m:
        continue
      if os.path.isdir(filename):
        subgcc = os.path.join(filename, "gcc")
        if os.path.exists(subgcc) and os.path.isdir(subgcc):
          if found:
            u.error("multiple gcc subdirs found "
                    "(%s and %s) -- cannot continue" % (found, filename))
          found = filename
    if not found:
      u.error("unable to locate gcc-* subdir in '.' -- can't continue")
    flag_gcc_subdir = found

  u.verbose(1, "gcc subdir is %s" % flag_gcc_subdir)
  subver = os.path.join(os.path.join(flag_gcc_subdir, "gcc"), "BASE-VER")
  try:
    with open(subver, "r") as f:
      lines = f.readlines()
  except IOError:
    u.error("open failed for %s" % subver)
  gcc_version = lines[0].strip()
  u.verbose(1, "gcc version appears to be %s" % gcc_version)


def setup_binutils():
  """Set up and build binutils."""
  # Set up binutils
  global binutils_subdir
  binutils_subdir = "binutils"
  if binutils_version:
    binutils_subdir = "binutils-%s" % binutils_version
    if not os.path.exists(binutils_subdir):
      docmd("wget http://ftpmirror.gnu.org/binutils/"
            "%s.tar.bz2" % binutils_subdir)
      docmd("tar jxf %s.tar.bz2" % binutils_subdir)
  else:
    if not os.path.exists(binutils_subdir):
      doscmd("git clone --depth 1 %s binutils" % binutils_git)
  # Configure binutils
  if not os.path.exists(binutils_build_dir):
    docmd("mkdir %s" % binutils_build_dir)
  dochdir(binutils_build_dir)
  doscmd("../%s/configure --prefix=%s --target=%s "
         "%s " % (binutils_subdir,
                  cross_prefix,
                  flag_target_arch,
                  flag_use_multilib))
  doscmd("make %s " % flag_parfactor)
  doscmd("make %s install" % flag_parfactor)
  dochdir("..")


def setup_cross():
  """Create cross dir if needed and add to path."""
  if not os.path.exists(cross_prefix):
    docmd("mkdir %s" % cross_prefix)
  epath = os.environ["PATH"]
  set_evar("PATH", "%s/bin:%s" % (cross_prefix, epath))


def patch_gmp_configure():
  """Ridiculous that this is needed..."""
  if not flag_dryrun:
    try:
      with open("gmp/configure", "r") as rf:
        lines = rf.readlines()
      try:
        with open("gmp/configure.hacked", "w") as wf:
          matcher = re.compile(r"^\s+M4=m4\-not\-needed\s*$")
          for line in lines:
            m = matcher.match(line)
            if m:
              wf.write("  echo M4=m4-not-needed\n")
            else:
              wf.write(line)
          wf.close()
          docmd("mv gmp/configure gmp/configure.orig")
          docmd("mv gmp/configure.hacked gmp/configure")
          docmd("chmod 0755 gmp/configure")
      except IOError:
        u.error("open failed for gmp/configure.hacked")
    except IOError:
      u.error("open failed for gmp/configure")
  else:
    u.verbose(0, "<applying gmp configure hack>")


def setup_prereqs():
  """Set up gcc prereqs."""
  # Run the contrib download script -- easier that way
  gmp = os.path.join(flag_gcc_subdir, "gmp")
  if not os.path.exists(gmp):
    dochdir(flag_gcc_subdir)
    docmd("./contrib/download_prerequisites")
    # Hack -- fix up gmp dir
    patch_gmp_configure()
    dochdir("..")


def mk_debug_configopts():
  fvars = ["CFLAGS", "CXXFLAGS", "CFLAGS_FOR_BUILD", "CXXFLAGS_FOR_BUILD"]
  opt = ""
  for v in fvars:
    opt += " %s=\"-O0 -g\"" % v
  return opt


def setup_gcc():
  """Configure and build gcc."""
  if not os.path.exists(gcc_build_dir):
    docmd("mkdir %s" % gcc_build_dir)
  dochdir(gcc_build_dir)
  dopt = ""
  if flag_debug_gcc:
    dopt = mk_debug_configopts()
  sropt = ""
  if sysroot:
    sropt = "--with-sysroot=%s" % sysroot
  else:
    if flag_do_only_gcc_build:
      sropt = ""
    else:
      sropt = "--with-glibc-version=2.20"
  doscmd("../%s/configure %s --prefix=%s --target=%s %s "
         "--enable-languages=%s --enable-libgo "
         "%s %s " % (flag_gcc_subdir,
                     dopt, cross_prefix,
                     flag_target_arch,
                     sropt, flag_langs,
                     flag_use_multilib, flag_use_bootstrap))
  doscmd("make %s all-gcc" % flag_parfactor)
  doscmd("make %s install-gcc" % flag_parfactor)
  dochdir("..")


def setup_kernel_headers():
  """Download and install kernel headers."""
  if not os.path.exists(kernel_version):
    doscmd("wget https://www.kernel.org/pub/linux/"
           "kernel/v3.x/%s.tar.xz" % kernel_version)
    docmd("tar xJf %s.tar.xz" % kernel_version)
  dochdir(kernel_version)
  archname = legal_arches[flag_target_arch]
  doscmd("make ARCH=%s INSTALL_HDR_PATH=%s/%s "
         "headers_install" % (archname, cross_prefix, flag_target_arch))
  dochdir("..")


def setup_glibc():
  """Configure and build glibc."""
  if not os.path.exists(glibc_build_dir):
    docmd("mkdir %s" % glibc_build_dir)
  glibc_subdir = "glibc-%s" % glibc_version
  if not os.path.exists(glibc_subdir):
    docmd("wget http://ftpmirror.gnu.org/glibc/"
          "%s.tar.bz2" % glibc_subdir)
    docmd("tar jxf %s.tar.bz2" % glibc_subdir)
  ta = flag_target_arch
  dochdir(glibc_build_dir)
  doscmd("../%s/configure --prefix=%s/%s "
         "--build=%s "
         "--host=%s "
         "--target=%s "
         "--with-headers=%s/%s/include "
         "%s "
         "libc_cv_forced_unwind=yes" % (glibc_subdir,
                                        cross_prefix, ta,
                                        "x86_64-pc-linux-gnu",
                                        ta, ta,
                                        cross_prefix, ta,
                                        flag_use_multilib))
  doscmd("make install-bootstrap-headers=yes install-headers")
  doscmd("touch %s/%s/include/gnu/stubs.h" % (cross_prefix, flag_target_arch))
  dochdir("..")


def setup_sysroot():
  """Set up target root environment for android compiler builds."""
  global sysroot
  if not flag_need_android_sysroot:
    return
  ta = legal_arches[flag_target_arch]
  pb = "prebuilts/ndk/current/platforms/android-21"
  sysroot = "%s/%s/arch-%s" % (flag_ndk_dir,
                               pb, ta)
  u.verbose(1, "setting sysroot to %s" % sysroot)


def perform():
  """Main guts of script."""
  others = not flag_do_only_gcc_build
  locate_gcc_subdir()
  setup_cross()
  if others:
    setup_kernel_headers()
    setup_binutils()
    setup_prereqs()
  setup_sysroot()
  setup_gcc()
  if others:
    setup_kernel_headers()
    setup_glibc()


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options]

    options:
    -h    show help message and exit
    -d    increase debug msg verbosity level
    -e    echo cmds before executing
    -s    show output from subcmds (ex: make)
    -S G  use GCC subdir 'G'
    -t T  build for target T
    -D    dryrun mode (echo commands but do not execute)
    -b N  use binutils version N
    -B    build only gcc, don't build other bits
    -Y    enable bootstrap
    -n    no parallelism in build
    -C    build debuggable gcc
    -M    pass --disable-multilib on configure
    -L Q  add language Q to enabled languages during configure step
    -N X  use sysroot derived from Android NDK at dir X (required for android targets)

    Example 1: set up build with toolchain repo, enable bootstrap

      %s -Y -t aarch64-linux-android

    Example 2: build gcc with go, no other bits

      %s -t x86_64-linux-gnu -e -B -L go

    """ % (me, me, me)
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_target_arch, flag_echo, flag_dryrun, flag_show_output
  global binutils_version, flag_parfactor, flag_do_only_gcc_build
  global flag_gcc_subdir, flag_debug_gcc, flag_langs
  global flag_need_android_sysroot, flag_ndk_dir
  global flag_use_multilib, flag_use_bootstrap

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "hdnest:b:N:DBMYCL:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-e":
      flag_echo = True
    elif opt == "-h":
      usage("usage:")
    elif opt == "-s":
      flag_show_output = True
    elif opt == "-B":
      flag_do_only_gcc_build = True
    elif opt == "-M":
      flag_use_multilib = "--disable-multilib"
    elif opt == "-Y":
      flag_use_bootstrap = ""
    elif opt == "-n":
      flag_parfactor = ""
    elif opt == "-b":
      u.verbose(0, "setting binutils version to %s" % arg)
      binutils_version = arg
    elif opt == "-N":
      if not os.path.exists(arg):
        usage("unable to access NDK dir %s" % arg)
      flag_ndk_dir = arg
    elif opt == "-C":
      flag_debug_gcc = True
    elif opt == "-S":
      u.verbose(0, "setting gcc_subdir to %s" % arg)
      flag_gcc_subdir = arg
    elif opt == "-D":
      flag_dryrun = True
      flag_echo = True
    elif opt == "-L":
      if arg not in legal_extralangs:
        usage("specified lang %s not part of legal extras list" % arg)
      flag_langs = "%s,%s" % (flag_langs, arg)
    elif opt == "-t":
      if arg not in legal_arches:
        usage("specified arch %s not part of legal list" % arg)
      flag_target_arch = arg

  if args:
    usage("unknown extra args")
  if not flag_target_arch:
    usage("select a target architecture")

  matcher = re.compile(r"^.*android.*$")
  m = matcher.match(flag_target_arch)
  if m:
    flag_need_android_sysroot = True
    u.verbose(1, "target arch is android, need sysroot")
  if flag_need_android_sysroot and not flag_ndk_dir:
    usage("android target specified, but no NDK dir given -- use -N option")


#
#......................................................................
#
# Main portion of script
#
parse_args()
u.setdeflanglocale()
perform()
exit(0)
