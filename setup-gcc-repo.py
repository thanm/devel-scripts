#!/usr/bin/python
"""Set up a GCC repository.

Download and configure a GCC repository. There are many options
available for downloading GCC -- there is subversion, GCC git (from
git://gcc.gnu.org/git/gcc.git), and github GCC
(https://github.com/gcc-mirror/gcc.git).

"""

import getopt
import os
import sys

import script_utils as u


# Echo command before executing
flag_echo = True

# Dry run mode
flag_dryrun = False

# Show command output (ex: make)
flag_show_output = False

# Select google 4_9 branch
flag_google = False

# Select vanilla 4_9 branch
flag_49_branch = False

# Select vanilla 5 branch
flag_5_branch = False

# Add sub-repos for GO-related projects
flag_dogo = False

# Which flavor
flag_flavor = None

# Use mirrors
flag_use_mirrors = False

# Legal flavors
flavors = {"svn": 1, "git": 1, "git-svn": 1}


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


def setup_binutils():
  """Set up binutils."""
  if os.path.exists("binutils"):
    u.verbose(0, "... 'binutils' already exists, skipping clone")
    return
  binutils_git = "git://sourceware.org/git/binutils-gdb.git"
  if flag_use_mirrors:
    binutils_git = "https://github.com/bminor/binutils-gdb"
  docmd("git clone --depth 1 %s binutils" % binutils_git)


def setup_go(targ):
  """Set up go-specific stuff."""
  if os.path.exists("gofrontend"):
    u.verbose(0, "... 'gofrontend' already exists, skipping clone")
    return
  docmd("git clone https://go.googlesource.com/gofrontend")
  dochdir(targ)
  docmd("rm -rf gcc/go/gofrontend")
  docmd("ln -s ../../../gofrontend/go gcc/go/gofrontend")
  docmd("rm -rf libgo")
  docmd("mkdir libgo")
  if flag_dryrun:
    u.verbose(0, "for f in GOFRONTEND/libgo/*; "
              "do ln -s $f libgo/`basename $f`; done")
  else:
    libgo = "../gofrontend/libgo"
    for item in os.listdir(libgo):
      docmd("ln -s ../../gofrontend/libgo/%s libgo/%s" % (item, item))
  dochdir("..")


def perform_git():
  """Create git repo."""
  targ = "gcc-trunk"
  if flag_flavor == "git" or flag_flavor == "git-svn":
    baseurl = "git://gcc.gnu.org/git/gcc.git"
    if flag_use_mirrors:
      baseurl = "https://github.com/gcc-mirror/gcc"
  if os.path.exists(targ):
    u.verbose(0, "... path %s already exists, skipping clone" % targ)
    return
  docmd("git clone %s %s" % (baseurl, targ))
  if flag_flavor == "git-svn":
    url = "http://gcc.gnu.org/svn/gcc/trunk"
    doscmd("git svn init %s" % url)
    doscmd("git config svn-remote.svn.fetch :refs/remotes/origin/master")
    doscmd("git svn rebase -l")
  if flag_google:
    dochdir(targ)
    docmd("git branch google origin/google")
    sp = ".git/info/sparse-checkout"
    if not flag_dryrun:
      try:
        with open(sp, "w") as f:
          f.write("gcc-4_9/")
      except IOError:
        u.error("open failed for %s" % sp)
    else:
      u.verbose(0, "echo 'gcc-4_9/' > %s" % sp)
    docmd("git checkout google")
    dochdir("..")
    docmd("ln -s google/gcc-4_9 gcc-4.9")


def perform_svn():
  """Create svn repo."""
  targ = "gcc-trunk"
  url = "svn://gcc.gnu.org/svn/gcc/trunk"
  if flag_google:
    targ = "gcc-google-4.9"
    url = "svn://gcc.gnu.org/svn/gcc/branches/google/gcc-4_9"
  elif flag_49_branch:
    targ = "gcc-4.9"
    url = "svn://gcc.gnu.org/svn/gcc/branches/gcc-4_9-branch"
  elif flag_5_branch:
    targ = "gcc-5"
    url = "svn://gcc.gnu.org/svn/gcc/branches/gcc-5-branch"
  docmd("svn co %s %s" % (url, targ))


def perform():
  """Guts of script."""
  if flag_flavor == "svn":
    perform_svn()
  else:
    perform_git()
    if flag_dogo:
      setup_go("gcc-trunk")
  setup_binutils()


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options]

    options:
    -d    increase debug msg verbosity level
    -e    echo cmds before executing
    -s    show output from git clone or svn checkout
    -D    dryrun mode (echo commands but do not execute)
    -f F  repository flavor F. Can be one of: svn|git|git-svn
    -M    use github mirrors where possible to speed things up
    -G    add sub-repos for go-related projects
    -g    select google 4_9 branch
    -b    select vanilla 4_9 branch
    -B    select vanilla 5 branch

    Example 1: setup gcc git repo off google/4_9 branch

      %s -f svn -g

    """ % (me, me)
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_echo, flag_dryrun, flag_google, flag_flavor
  global flag_show_output, flag_49_branch, flag_5_branch
  global flag_dogo, flag_use_mirrors

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "dbBeDGMgsf:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-e":
      flag_echo = True
    elif opt == "-g":
      flag_google = True
    elif opt == "-G":
      flag_dogo = True
    elif opt == "-M":
      flag_use_mirrors = True
    elif opt == "-b":
      flag_49_branch = True
    elif opt == "-B":
      flag_5_branch = True
    elif opt == "-s":
      flag_show_output = True
    elif opt == "-f":
      if arg not in flavors:
        usage("flavor %s not in set of legal "
              "flavors: %s" % (arg, " ".join(flavors.keys())))
      flag_flavor = arg
    elif opt == "-D":
      flag_dryrun = True
      flag_echo = True

  if args:
    usage("unknown extra args")
  if not flag_flavor:
    usage("select a flavor")
  if flag_49_branch and flag_google:
    usage("pick either -b or -g (not both)")
  if flag_49_branch and flag_flavor != "svn":
    usage("-b option requires -f svn")
  if flag_5_branch and flag_flavor != "svn":
    usage("-B option requires -f svn")
  if flag_5_branch and flag_49_branch:
    usage("select one of -B / -b but not both")


#
#......................................................................
#
# Main portion of script
#
parse_args()
u.setdeflanglocale()
perform()
exit(0)
