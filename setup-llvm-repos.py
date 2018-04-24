#!/usr/bin/python
"""Script to create LLVM trunk devel subvolume or snapshot.

Creates BTRFS subvolume with trunk git-on-svn client, plus binutils, then
runs cmake to set up ninja build. More details at:

   http://llvm.org/docs/GettingStarted.html
   http://llvm.org/docs/DeveloperPolicy.html

This script has two modes: initial "-r" run to create master subvolume,
then "-s" mode to create working snapshot (also kicks off cmake and build
in snapshot).

Todos:
- add build.bootstrap.rel and build.bootstrap.opt build dirs
  that pick up compilers from build.opt and build.rel

"""

import getopt
import multiprocessing
import os
import re
import sys

import script_utils as u


# Name of root subvolume
flag_subvol = None

# Name of snapshot
flag_snapshot = None

# User
flag_user = None

# Whether to do binutils build in new snapshot
flag_binutils_build = True

# Whether configure in snapshot/subvol
flag_configure = False

# Whether to run ninja in new snapshot
flag_run_ninja = True

# Echo command before executing
flag_echo = True

# Dry run mode
flag_dryrun = False

# SCM flavor: git, svn or git-svn (default: git-svn)
flag_scm_flavor = "git-svn"

# Default CMake build type
flag_cmake_type = "Debug"

# Default CMake compiler selection
flag_cmake_ccomp = ""

# Update master subvolume before snapshotting
flag_do_fetch = False

# Whether to include clang tools in repo
flag_include_tools = True

# Whether to include llgo in repo
flag_include_llgo = False

# Whether to include polly in repo
flag_include_polly = False

# Whether to include libcxx in repo
flag_include_libcxx = False

# Run cmake cmds in parallel
flag_parallel = True

# Place from which to copy binutils
flag_binutils_location = None

# SSD root or root dir
ssdroot = None

# If false, no btrfs stuff
flag_btrfs = True

# Various repositories
llvm_rw_svn = "https://REPLACE_WITH_USER@llvm.org/svn/llvm-project"
llvm_git_on_svn = "https://llvm.org/svn/llvm-project"
llvm_ro_svn = "http://llvm.org/svn/llvm-project"
binutils_git = "git://sourceware.org/git/binutils-gdb.git"
llvm_git = "http://llvm.org/git/llvm.git"
clang_git = "http://llvm.org/git/clang.git"
clang_tools_git = "http://llvm.org/git/clang-tools-extra.git"
llgo_git = "http://llvm.org/git/llgo.git"
polly_git = "http://llvm.org/git/polly.git"
polly_svn = "http://llvm.org/svn/llvm-project/polly"
libcxx_svn = "https://llvm.org/svn/llvm-project/libcxx"
libcxx_git = "http://llvm.org/git/libcxx.git"
libcxxabi_svn = "https://llvm.org/svn/llvm-project/libcxxabi"
libcxxabi_git = "http://llvm.org/git/libcxxabi.git"
compiler_rt_svn = "https://llvm.org/svn/llvm-project/compiler-rt"
compiler_rt_git = "http://llvm.org/git/compiler-rt.git"

# Clang compilers. Must be full path.
clang_c_compiler = "/usr/bin/clang-3.9"
clang_cxx_compiler = "/usr/bin/clang++-3.9"

# Gcc compilers. Must be full path.
gcc_c_compiler = "/usr/bin/gcc-4.8"
gcc_cxx_compiler = "/usr/bin/g++-4.8"

# Coverage related stuff
covopt = "--coverage"
cov_cmake_ccomp = ""

# Table with info on various cmake flavors. Key is build flavor,
# value is a direct with various settings. Keys in this dict include:
#
#    cmflav:      cmake flavor (ex: Release, Debug, etc). Set to
#                 None for the default.
#
#    ccflav:      C/C++ compiler to use for the build. Possible
#                 values include "clang", "gcc", "def" (to skip
#                 explicitly setting CMAKE_C/CXX_COMPILER) and
#                 "bootstrap=%B" where %B is another build dir.
#
#    extra:       extra cmake arguments for this build.
#
#    early:       if present, run cmake for this build at snapshot
#                 creation time
#
# Notes:
# - coverage testing works better with installed "cc"
# - release build is done with gcc
#
legal_tags = {"cmflav": 1, "ccflav": 1, "extra": 1, "early": 1}
cmake_flavors = {

    "opt": {"cmflav": None,
            "early": 1,
            "ccflav": "clang",
            "extra": None},

    "dbg": {"cmflav": None,
            "early": 1,
            "ccflav": "clang",
            "extra": ("-DCXX_SUPPORTS_COVERED_SWITCH_DEFAULT_FLAG=0 "
                      "-DCMAKE_C_FLAGS=\'-g -O0\' "
                      "-DCMAKE_CXX_FLAGS=\'-g -O0\'")},

    "rel": {"cmflav": "Release",
            "early": 1,
            "ccflav": "gcc",
            "extra": None},

    "cov": {"cmflav": None,
            "ccflav": "def",
            "extra": ("-DCMAKE_C_FLAGS=\'%s\' "
                      "-DCMAKE_CXX_FLAGS=\'%s\'" % (covopt, covopt))},

    "clbootstrap.rel": {"cmflav": "Release",
                        "ccflav": "gcc",
                        "extra": "-DCLANG_ENABLE_BOOTSTRAP=On"},
}


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
  if flag_echo or flag_dryrun:
    sys.stderr.write("cd " + thedir + "\n")
  if flag_dryrun:
    return
  try:
    os.chdir(thedir)
  except OSError as err:
    u.error("chdir failed: %s" % err)


def do_llvmtool_create(top, tool, pdir, gitloc, svnloc):
  """Create new sub-repo within llvm/tools or llvm/projects."""
  dochdir("%s/llvm/%s" % (top, pdir))
  if flag_scm_flavor == "git":
    doscmd("svn co %s/%s/trunk %s" % (llvm_ro_svn, tool))
  else:
    doscmd("git clone %s %s" % (gitloc, tool))
    if flag_scm_flavor == "git-svn":
      dochdir("%s" % tool)
      doscmd("git svn init %s/trunk "
             "--username=%s" % (svnloc, flag_user))
      doscmd("git config svn-remote.svn.fetch :refs/remotes/origin/master")
      doscmd("git svn rebase -l")


def do_subvol_create():
  """Create new LLVM trunk subvolume if needed."""
  sv = "%s/%s" % (ssdroot, flag_subvol)
  if os.path.exists(sv):
    u.verbose(1, "subvolume %s already exists, skipping creation" % sv)
    return
  here = os.getcwd()
  if flag_btrfs:
    docmd("snapshotutil.py mkvol %s" % flag_subvol)
  else:
    docmd("mkdir %s" % flag_subvol)
  dochdir(ssdroot)
  dochdir(flag_subvol)
  top = "%s/%s" % (ssdroot, flag_subvol)

  # First llvm
  if flag_scm_flavor == "svn":
    doscmd("svn co %s/llvm/trunk llvm" % llvm_rw_svn)
  else:
    doscmd("git clone %s" % llvm_git)
    if flag_scm_flavor == "git-svn":
      dochdir("llvm")
      doscmd("git svn init %s/llvm/trunk "
             "--username=%s" % (llvm_git_on_svn, flag_user))
      doscmd("git config svn-remote.svn.fetch :refs/remotes/origin/master")
      doscmd("git svn rebase -l")

  # Next clang
  dochdir("%s/llvm/tools" % top)
  if flag_scm_flavor == "svn":
    doscmd("svn co %s/cfe/trunk clang" % llvm_ro_svn)
  else:
    doscmd("git clone %s" % clang_git)
    if flag_scm_flavor == "git-svn":
      dochdir("clang")
      doscmd("git svn init %s/cfe/trunk "
             "--username=%s" % (llvm_git_on_svn, flag_user))
      doscmd("git config svn-remote.svn.fetch :refs/remotes/origin/master")
      doscmd("git svn rebase -l")

  # Now clang tools
  if flag_include_tools:
    dochdir("%s/llvm/tools/clang/tools" % top)
    if flag_scm_flavor == "git":
      doscmd("svn co %s/clang-tools-extra/trunk extra" % llvm_ro_svn)
    else:
      doscmd("git clone %s extra" % clang_tools_git)
      if flag_scm_flavor == "git-svn":
        dochdir("extra")
        doscmd("git svn init %s/clang-tools-extra/trunk "
               "--username=%s" % (llvm_git_on_svn, flag_user))
        doscmd("git config svn-remote.svn.fetch :refs/remotes/origin/master")
        doscmd("git svn rebase -l")

  # Now llgo
  if flag_include_llgo:
    do_llvmtool_create(top, "llgo", "tools", llgo_git, llgo_svn)

  # Now polly
  if flag_include_polly:
    do_llvmtool_create(top, "polly", "tools", polly_git, polly_svn)

  # Now libcxx
  if flag_include_libcxx:
    do_llvmtool_create(top, "libcxx", "projects", libcxx_git, libcxx_svn)
    do_llvmtool_create(top, "libcxxabi", "projects", libcxxabi_git, libcxxabi_svn)

  # Now compiler-rt
  do_llvmtool_create(top, "compiler-rt", "projects", compiler_rt_git, compiler_rt_svn)

  # Now binutils. NB: git clone can be incredibly slow sometimes.
  # Consider adding --depth 1 maybe?
  dochdir(top)
  if flag_binutils_location:
    doscmd("cp -r %s binutils" % flag_binutils_location)
  else:
    doscmd("git clone %s binutils" % binutils_git)
  dochdir(here)


def do_fetch(flavor, where):
  """Update with svn or git."""
  here = os.getcwd()
  dochdir(where)
  if flavor == "git":
    docmd("git fetch")
  elif flavor == "git-svn":
    docmd("git fetch")
    docmd("git svn rebase -l")
  else:
    docmd("svn update")
  dochdir(here)


def fetch_in_volume():
  """Update subvolume with svn or git."""
  top = "%s/%s" % (ssdroot, flag_subvol)
  dochdir(top)
  # First binutils (which is only git)
  do_fetch("git", "binutils")
  dochdir("llvm")
  # Next llvm stuff
  tofind = ".git"
  if flag_scm_flavor == "svn":
    tofind = ".svn"
  lines = u.docmdlines("find . -depth -name %s -print" % tofind)
  for line in lines:
    do_fetch(flag_scm_flavor, line.strip())
  dochdir(top)


def bootstrap_tooldir(flav):
  """Return tool directory for bootstrap build."""
  fd = cmake_flavors[flav]
  ccflav = fd["ccflav"]
  rx = re.compile(r"^bootstrap\.(\S+)$")
  m = rx.match(ccflav)
  if not m:
    return None
  tb = m.group(1)
  tbdir = "%s/%s/%s" % (ssdroot, flag_subvol, tb)
  return tbdir


def select_cmake_type(flav):
  """Return cmake type for build."""
  fd = cmake_flavors[flav]
  if "cmflav" not in fd:
    u.error("internal error: build flavor %s has no cmflav setting" % flav)
  cmflav = fd["cmflav"]
  if not cmflav:
    cmflav = flag_cmake_type
  return cmflav


def select_cmake_extras(flav):
  """Return cmake extras for build."""
  fd = cmake_flavors[flav]
  if "extra" not in fd:
    return ""
  cmflav = fd["extra"]
  if not cmflav:
    return ""
  return cmflav


def select_dyld_library_path(flav):
  """Return DYLD_LIBRARY_PATH for cmake if needed."""
  tbdir = bootstrap_tooldir(flav)
  if not tbdir:
    return ""
  return "env DYLD_LIBRARY_PATH=%s/lib" % tbdir


def select_compiler_flavor(flav):
  """Returns string with cmake compiler setup."""
  extrastuff = ""
  if flav not in cmake_flavors:
    u.error("internal error -- flavor %s not in cmake_flavors" % flav)
  fd = cmake_flavors[flav]
  if "ccflav" not in fd:
    u.error("internal error: build flavor %s has no ccflav setting" % flav)
  ccflav = fd["ccflav"]
  tbdir = bootstrap_tooldir(flav)
  if ccflav == "gcc":
    build_c_compiler = gcc_c_compiler
    build_cxx_compiler = gcc_cxx_compiler
  elif ccflav == "clang":
    build_c_compiler = clang_c_compiler
    build_cxx_compiler = clang_cxx_compiler
  elif ccflav == "def":
    return ""
  elif tbdir:
    build_c_compiler = "%s/bin/clang" % tbdir
    build_cxx_compiler = "%s/bin/clang++" % tbdir
    extrastuff = ("-DCMAKE_RANLIB=%s/bin/llvm-ranlib "
                  "-DCMAKE_AR=%s/bin/llvm-ar " % (tbdir, tbdir))
  else:
    u.error("internal error -- bad ccflav setting %s" % ccflav)
  return ("%s-DCMAKE_C_COMPILER=%s -DCMAKE_ASM_COMPILER=%s "
          "-DCMAKE_CXX_COMPILER=%s" % (extrastuff,
                                       build_c_compiler,
                                       build_c_compiler,
                                       build_cxx_compiler))


def emit_cmake_cmd_script(flav, targdir):
  """Emit/archive cmake cmds for flav."""
  bpath = ("LLVM_BINUTILS_INCDIR=%s/%s"
           "/binutils/include" % (ssdroot, targdir))
  u.verbose(0, "...kicking off cmake for %s in parallel..." % flav)
  dyldsetting = select_dyld_library_path(flav)
  ccomp = select_compiler_flavor(flav)
  cmake_type = select_cmake_type(flav)
  extra = select_cmake_extras(flav)
  limitlink = "LLVM_PARALLEL_LINK_JOBS=8"
  cmake_cmd = ("%s cmake -D%s -DCMAKE_BUILD_TYPE=%s -D%s %s %s -G Ninja "
               "../llvm" % (dyldsetting, limitlink,
                            cmake_type, bpath, ccomp, extra))
  if flag_dryrun:
    print "+++ archiving cmake cmd: %s" % cmake_cmd
  else:
    try:
      with open("./.cmake_cmd", "w") as wf:
        wf.write(cmake_cmd)
        wf.write("\n")
    except IOError:
      u.error("open/write failed for .cmake_cmd")
  return cmake_cmd


def emit_rebuild_scripts(flav, targdir):
  """Emit top-level clean, rebuild scripts."""
  bpath = "%s/%s/build.%s" % (ssdroot, targdir, flav)
  if flag_dryrun:
    print "+++ archiving clean + build cmds"
    return

  # Emit clean script
  try:
    with open("./.clean.sh", "w") as wf:
      wf.write("#!/bin/sh\n")
      wf.write("set -e\n")
      wf.write("cd %s || exit 9\n" % bpath)
      wf.write("cd ../binutils-build\n")
      wf.write("echo ... cleaning binutils-build\n")
      wf.write("make clean 1> ../build.%s/.clean.err 2>&1\n" % flav)
      wf.write("echo ... cleaning llvm\n")
      wf.write("cd ../build.%s\n" % flav)
      wf.write("ninja clean 1>> .clean.err 2>&1\n")
      wf.write("exit 0\n")
  except IOError:
    u.error("open/write failed for .clean.sh")

  # Emit build-all script
  try:
    with open("./.build-all.sh", "w") as wf:
      wf.write("#!/bin/sh\n")
      wf.write("set -e\n")
      wf.write("cd %s || exit 9\n" % bpath)
      wf.write("cd ../binutils-build\n")
      wf.write("echo ... running make in binutils-build\n")
      wf.write("NP=`nproc`\n")
      wf.write("make -j${NP} 1> ../build.%s/.binutils-build.err 2>&1\n" % flav)
      wf.write("make -j${NP} all-gold 1> "
               "../build.%s/.binutils-build.err 2>&1\n" % flav)
      wf.write("cd ../build.%s\n" % flav)
      wf.write("echo ... running ninja build\n")
      wf.write("ninja\n")
      wf.write("exit 0\n")
  except IOError:
    u.error("open/write failed for .build-all.sh")

  # Emit clean-and-build-all script
  try:
    with open("./.clean-and-build-all.sh", "w") as wf:
      wf.write("#!/bin/sh\n")
      wf.write("set -e\n")
      wf.write("cd %s || exit 9\n" % bpath)
      wf.write("sh ./.clean.sh\n")
      wf.write("sh ./.build-all.sh\n")
      wf.write("exit 0\n")
  except IOError:
    u.error("open/write failed for .cmake_cmd")


def do_configure_binutils(targdir):
  """Create binutils bin dir and run configure."""
  dochdir(ssdroot)
  dochdir(targdir)
  docmd("mkdir binutils-build")
  dochdir("binutils-build")
  doscmd("../binutils/configure --enable-gold "
         "--enable-plugins --disable-werror")
  dochdir("..")


def run_cmake(builddir, cmake_cmd):
  """Cmake run helper."""
  try:
    os.chdir(builddir)
  except OSError as err:
    u.warning("chdir failed: %s" % err)
    return 1
  rv = u.doscmd(cmake_cmd, True)
  if not rv:
    u.warning("cmd command returned bad status: %s" % cmake_cmd)
    return 1
  return 0


def do_setup_cmake(targdir):
  """Run cmake in each of the bin dirs."""
  dochdir(ssdroot)
  dochdir(targdir)
  pool = None
  if flag_parallel:
    nworkers = len(cmake_flavors)
    pool = multiprocessing.Pool(processes=nworkers)
  results = []
  for flav in cmake_flavors:
    docmd("mkdir build.%s" % flav)
    dochdir("build.%s" % flav)
    emit_rebuild_scripts(flav, targdir)
    cmake_cmd = emit_cmake_cmd_script(flav, targdir)
    if flag_parallel and not flag_dryrun:
      u.verbose(0, "...kicking off cmake for %s in parallel..." % flav)
      builddir = "%s/%s/build.%s" % (ssdroot, targdir, flav)
      r = pool.apply_async(run_cmake, [builddir, cmake_cmd])
      results.append(r)
    else:
      doscmd(cmake_cmd)
    dochdir("..")
  nr = len(results)
  rc = 0
  for idx in range(0, nr):
    r = results[idx]
    u.verbose(1, "waiting on result %d" % idx)
    res = r.get(timeout=600)
    if res != 0:
      rc = 1
  if rc:
    u.error("one or more cmake cmds failed")


def do_snapshot_create():
  """Create new LLVM trunk snapshot."""
  if flag_do_fetch:
    fetch_in_volume()
  if flag_btrfs:
    docmd("snapshotutil.py mksnap %s %s" % (flag_subvol, flag_snapshot))


def do_configure():
  """Run configure/setup/cmake in snapshot or subvol."""
  if flag_do_fetch:
    fetch_in_volume()
  dochdir(ssdroot)
  targdir = flag_subvol
  if flag_snapshot:
    targdir = flag_snapshot
  do_configure_binutils(targdir)
  do_setup_cmake(targdir)


def do_build():
  """Perform build in snapshot or subvol."""
  dochdir(ssdroot)
  if flag_snapshot:
    dochdir(flag_snapshot)
  else:
    dochdir(flag_subvol)
  if flag_binutils_build:
    dochdir("binutils-build")
    nworkers = multiprocessing.cpu_count()
    doscmd("make -j%d" % nworkers)
    doscmd("make -j%d all-gold" % nworkers)
    dochdir("..")
  else:
    u.verbose(0, "... binutils build stubbed out")
  if flag_run_ninja:
    dochdir("build.opt")
    docmd("ninja")
    dochdir("..")
  else:
    u.verbose(0, "... ninja build stubbed out")


def perform():
  """Main driver routine."""
  do_subvol_create()
  if flag_snapshot:
    do_snapshot_create()
  if flag_configure:
    do_configure()
  do_build()


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options]

    options:
    -d    increase debug msg verbosity level
    -r R  root subvolume is R
    -s S  snapshot is S
    -c    run configure in subvol, not snapshot
    -n    stub out ninja build
    -N    stub out binutils build
    -q    quiet mode (do not echo commands before executing)
    -S X  use SCM flavor X (either git, svn, or git-svn). Def: git-svn
    -B D  copy binutils from dir D instead of performing 'git clone'
    -D    dryrun mode (echo commands but do not execute)
    -X    set default build type to RelWithDebInfo
    -T    avoid setting up clang tools
    -J    run cmake steps serially (default is in parallel)
    -G    include llgo when setting up repo
    -P    include polly when setting up repo
    -L    include libcxx when setting up repo
    -F    run 'git fetch' or 'svn update' in subvolume
          before creating snapshot
    -M    disable BTRFS (assume regular dirs). Implies -c.

    Example 1: creates new subvolume 'llvm-trunk', no build or configure

      %s -r llvm-trunk

    Example 2: snapshot subvol 'llvm-trunk' creating 'llvm-trunk-snap' w/ builds

      %s -r llvm-trunk -c -s llvm-snap

    Example 3: snapshot subvol 'llvm-trunk' to create 'llvm-gronk',
               stubbing out ninja build

      %s -r llvm-trunk -c -n -s llvm-gronk

    Example 4: create new subvol, then configure and build there
               instead of later in snapshot

      %s -r llvm-trunk -c

    """ % (me, me, me, me, me)
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_subvol, flag_snapshot, flag_echo, flag_dryrun, flag_configure
  global flag_scm_flavor, flag_cmake_type, flag_include_llgo
  global flag_do_fetch, flag_include_tools, flag_include_polly, flag_parallel
  global flag_binutils_build, flag_run_ninja, llvm_rw_svn, flag_user
  global ssdroot, flag_binutils_location, flag_btrfs, flag_include_libcxx

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "DPGJB:S:FTLMXqcdnNs:r:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-N":
      flag_binutils_build = False
    elif opt == "-n":
      flag_run_ninja = False
    elif opt == "-c":
      flag_configure = True
    elif opt == "-M":
      flag_configure = True
      flag_btrfs = False
    elif opt == "-B":
      if os.path.exists(arg) and os.path.isdir(arg):
        u.verbose(1, "drawing binutils from %s" % arg)
        flag_binutils_location = arg
      else:
        usage("inaccessable/unknown binutils location %s" %arg)
    elif opt == "-S":
      if arg != "git" and arg != "svn" and arg != "git-svn":
        usage("illegal SCM flavor %s" % arg)
      flag_scm_flavor = arg
    elif opt == "-q":
      flag_echo = False
    elif opt == "-D":
      flag_dryrun = True
    elif opt == "-G":
      flag_include_llgo = True
    elif opt == "-P":
      flag_include_polly = True
    elif opt == "-L":
      flag_include_libcxx = True
    elif opt == "-F":
      flag_do_fetch = True
    elif opt == "-J":
      flag_parallel = True
    elif opt == "-X":
      flag_cmake_type = "RelWithDebInfo"
    elif opt == "-T":
      flag_include_tools = False
    elif opt == "-r":
      flag_subvol = arg
    elif opt == "-s":
      flag_snapshot = arg

  if args:
    usage("unknown extra args")
  if not flag_subvol:
    usage("specify subvol name with -r")
  if flag_snapshot and not flag_subvol:
    usage("specify subvol name with -r")
  if not flag_btrfs and flag_snapshot:
    usage("can't use -s with -M")
  lines = u.docmdlines("whoami")
  flag_user = lines[0]
  if flag_user == "root":
    u.error("please don't run this script as root")
  llvm_rw_svn = re.sub("REPLACE_WITH_USER", flag_user, llvm_rw_svn)
  u.verbose(2, "llvm_rw_svn is: %s" % llvm_rw_svn)

  # Validate cmake_flavors
  for tag, d in cmake_flavors.iteritems():
    for subtag in d:
      if subtag not in legal_tags:
        u.error("internal error: cmake_flavors entry %s "
                "has unknown tag %s" % (tag, subtag))

  # Set ssd root
  here = os.getcwd()
  if flag_btrfs:
    ssdroot = u.determine_btrfs_ssdroot(here)
  else:
    ssdroot = here


#
#......................................................................
#
# Main portion of script
#
parse_args()
u.setdeflanglocale()
perform()
exit(0)
