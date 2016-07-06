#!/usr/bin/python
"""Perform multiple Android builds in a single repo.

This script cycles through a set of different build targets within an
Android repo, performs a build for each target, and captures the
output of the builds. It is intended to help with compiler toolchain
testing.

The process of setting up a given build is made somewhat more
complicated by the fact that for normal developers, selecting a build
config is done via the "lunch" command (which is essentially a
bash-only construct), and builds themselves are also done via bash
functions. We get around the first problem by capturing the effects of
the lunch command via a separate bash command, then use the wrapper
"mmm.py" for build invocation. This is hacky but seems to do the job,

A significant obstacle to testing new GCC prebuilts is that there are
many lunch targets that default most everything to clang -- doing a build
tests clang a lot and gcc only a little. To work around this, the script
supports "munging" some of the core makefiles to reset the default to gcc
from clang. Doing this is problematic, since GCC's enforcement of warnings
can be slightly different from clang's (hence the code also adds "-Wno-error"
as part of the munging).

In this initial version, the assumption is that we're not going to
make any changes to the repo branch/manifest/git-contents as we cycle
from build to build. At some future point it would probably be a good
idea to add in the capability to select a new branch (ex:
"mnc-release") for a given device.

Todo:
- support for internal-tree builds (edison-userdebug)
- support for flashing results of build to specific device
  (read devtags perhaps)
- support for repo reinit, e.g. redo repo with specific branch,
  then 'repo sync -l -c -j16' before build
- support for clean repo recreation, e.g. delete all dir contents
  and do repo init + sync from scratch

"""

import copy
import getopt
import os
import re
import shutil
import sys
import time

import script_utils as u

# Echo commands before executing
flag_echo = False

# Echo commands before executing
flag_dryrun = False

# Clean following builds
flag_do_clean = True

# Munge makefiles to enable more gcc compilation
flag_munge_make = True

# Early exit after makefile munge
flag_postmunge_exit = False

# Perform the build
flag_do_build = True

# Perform specified list of builds
flag_targets = []

# Flash builds to connected devices
flag_do_flash = False

# Verify results of flash
flag_do_flashverify = False

# Run checkbuild (compiles a lot more)
flag_checkbuild = False

# Set of builds to run. Entries with a value of 0 are stubbed out
# by default (can only be run with -S option).
available_builds = {"aosp_shamu-userdebug": 1,
                    "aosp_arm64-eng": 1,
                    "aosp_x86-eng": 1,
                    "aosp_mips-userdebug": 1,
                    "aosp_mips64-userdebug": 1,
                    "aosp_fugu-userdebug": 1,
                    "aosp_angler-userdebug": 1,
                    "aosp_flounder-userdebug": 1,
                    "edison-userdebug": 0}

# Used to cache environment
saved_env = {}

# Invoke mmma X instead of top level 'm'
flag_mmma_target = None

# Parallel factor
flag_parfactor = 40

# Stop after first failure
flag_exit_on_err = False

# Maps device tag (ex: N6) to serial number
tag_to_serial = {}

# Maps device codename (ex: hammerhead) to tag (ex: N5)
codename_to_tag = {}

# Filter/munge recipe to smooth out gcc compilations
flagmunge = """
ifneq ($(my_clang),true)
  warning_flags_not_currently_supported_by_gcc := -Wno-typedef-redefinition -Wno-gnu-variable-sized-type-not-at-end -Wno-constant-logical-operand -no-integrated-as
  warning_flags_to_eliminate := -Werror=return-type -Werror=date-time
  my_cflags := $(filter-out $(warning_flags_not_currently_supported_by_gcc),$(my_cflags))
  my_cflags := $(filter-out $(warning_flags_to_eliminate),$(my_cflags))
  my_cflags := $(my_cflags) -fpermissive -Wno-error
endif
"""

# Makefile munge table.
munge_table = {"build/core/envsetup.mk":
               [("remove", "USE_CLANG_PLATFORM_BUILD := true"),
                ("append", "USE_CLANG_PLATFORM_BUILD := false")],
               "build/core/binary.mk":
               [("insert-before", "ifeq ($(my_fdo_build), true)",
                 "warning_flags_not_currently_supported_by_gcc", flagmunge)]}


def docmd(cmd):
  """Execute a command."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmd(cmd)


def docmdnf(cmd):
  """Execute a command."""
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
  return u.doscmd(cmd, True)


def docmdout(cmd, outfile, nf):
  """Execute a command redirecting output to a file."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + " > " + outfile + "\n")
  if flag_dryrun:
    return
  return u.docmdout(cmd, outfile, nf)


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


def remove_from_file_if_present(mfile, todel):
  """Remove specified line from makefile if present."""
  if not os.path.exists(mfile):
    u.error("bad entry in munge makefile table-- %s "
            "does not appear to exist" % mfile)
  mfile_new = "%s.munged" % mfile
  found = False
  u.verbose(2, "examining %s in remove munge" % mfile)
  with open(mfile, "r") as rf:
    with open(mfile_new, "w") as wf:
      lines = rf.readlines()
      linecount = 0
      for line in lines:
        linecount += 1
        sline = line.strip()
        if sline == todel:
          found = True
          u.verbose(2, "found todel %s at line %d "
                    "in %s" % (todel, linecount, mfile))
          continue
        wf.write(line)
  if found:
    docmd("mv -f %s %s" % (mfile_new, mfile))
    return True
  return False


def append_to_file_if_not_already_present(mfile, toadd):
  """Add specified line to makefile if not already present."""
  if not os.path.exists(mfile):
    u.error("bad entry in munge makefile table-- %s "
            "does not appear to exist" % mfile)
  mfile_new = "%s.munged" % mfile
  u.verbose(2, "examining %s in append munge" % mfile)
  with open(mfile, "r") as rf:
    with open(mfile_new, "w") as wf:
      lines = rf.readlines()
      linecount = 0
      for line in lines:
        linecount += 1
        sline = line.strip()
        if sline == toadd:
          u.verbose(2, "found toadd %s at line %d "
                    "in %s" % (toadd, linecount, mfile))
          return False
        wf.write(line)
      u.verbose(2, "appending toadd %s to %s "
                "at line %d" % (toadd, mfile, linecount))
      wf.write("%s\n" % toadd)
  docmd("mv -f %s %s" % (mfile_new, mfile))
  return True


def insert_before_if_not_already_present(mfile, insertloc, keyword, toadd):
  """Insert specified chunk of text to makefile if not already present."""
  if not os.path.exists(mfile):
    u.error("bad entry in munge makefile table-- %s "
            "does not appear to exist" % mfile)
  mfile_new = "%s.munged" % mfile
  u.verbose(2, "examining %s in insert-before munge" % mfile)
  with open(mfile, "r") as rf:
    with open(mfile_new, "w") as wf:
      lines = rf.readlines()
      linecount = 0
      for line in lines:
        linecount += 1
        # Already present?
        linewords = line.split()
        for word in linewords:
          if word == keyword:
            u.verbose(2, "found keyword %s at line %d "
                      "in %s" % (keyword, linecount, mfile))
            return False
        # At insertloc?
        if line.strip() == insertloc:
          u.verbose(2, "adding %s insert-before text at line %d "
                    "in %s " % (keyword, linecount, mfile))
          wf.write("%s\n" % toadd)
          wf.write(line)
        else:
          wf.write(line)
  docmd("mv -f %s %s" % (mfile_new, mfile))
  return True


def restore_single_makefile(mfile):
  """Insure that specified makefile is unmunged."""
  u.verbose(1, "examining makefile %s for restore" % mfile)
  components = mfile.split("/")
  bpath = "/".join(components[1:])
  os.chdir("build")
  lines = u.docmdlines("git diff --exit-code --name-status %s" % bpath, True)
  if not lines:
    u.verbose(1, "restoring munged makefile %s" % mfile)
    docmd("git checkout %s" % bpath)
  os.chdir("..")


def munge_single_makefile(mfile, operations):
  """Modify a single makefile."""
  u.verbose(1, "examining makefile %s for munge" % mfile)
  for tup in operations:
    opname = tup[0]
    item = tup[1]
    if opname == "remove":
      was_present = remove_from_file_if_present(mfile, item)
      if not was_present:
        u.verbose(1, "bailing out early for makefile %s" % mfile)
        break
    elif opname == "append":
      already_there = append_to_file_if_not_already_present(mfile, item)
      if not already_there:
        u.verbose(1, "bailing out early for makefile %s" % mfile)
        break
    elif opname == "insert-before":
      already_there = insert_before_if_not_already_present(mfile, item,
                                                           tup[2], tup[3])
      if not already_there:
        u.verbose(1, "bailing out early for makefile %s" % mfile)
        break
    else:
      u.error("internal error -- unknown munge op %s" % opname)


def munge_makefiles_if_needed():
  """Modify build makefiles to enable more gcc compilation."""
  u.verbose(1, "munging makefiles")
  for mfile, operations in munge_table.iteritems():
    if flag_munge_make:
      munge_single_makefile(mfile, operations)
    else:
      restore_single_makefile(mfile)
  if flag_postmunge_exit:
    print "EARLY EXIT IN munge_makefiles_if_needed"
    exit(0)


def load_environment(old_env, new_env):
  """Load up new copy of environment from a dict."""
  u.verbose(2, "load_environment invoked")
  # Find new vars, modified vars, deleted vars
  added_vars = {}
  modified_vars = {}
  deleted_vars = {}
  for v in new_env:
    if v not in old_env:
      added_vars[v] = 1
    else:
      if new_env[v] != old_env[v]:
        modified_vars[v] = 1
  for v in old_env:
    if v not in new_env:
      deleted_vars[v] = 1
  u.verbose(2, "deleting vars: %s" % " ".join(sorted(deleted_vars.keys())))
  for v in deleted_vars:

    os.unsetenv(v)
    os.environ.pop(v, None)
  u.verbose(2, "adding vars: %s" % " ".join(sorted(added_vars.keys())))
  for v in added_vars:
    os.putenv(v, new_env[v])
    os.environ[v] = new_env[v]
  u.verbose(2, "modifying vars: %s" % " ".join(sorted(modified_vars.keys())))
  for v in modified_vars:
    os.putenv(v, new_env[v])
    os.environ[v] = new_env[v]


def save_environment():
  """Save a copy of environment."""
  global saved_env
  u.verbose(1, "saving copy of environment")
  saved_env = copy.deepcopy(os.environ)


def read_env_cachefile(cachefile):
  """Read environment from cache file into dict."""
  # Read results
  u.verbose(1, "reading results from %s" % cachefile)
  env_dict = {}
  try:
    with open(cachefile, "r") as rf:
      regex = re.compile(r"^([^=]+)\=(.*)$")
      lines = rf.readlines()
      for line in lines:
        m = regex.match(line)
        if not m:
          u.warning("unable to parse environment line %s" % line)
          continue
        varname = m.group(1)
        setting = m.group(2)
        u.verbose(2, "caching %s=%s" % (varname, setting))
        env_dict[varname] = setting
  except IOError:
    u.error("unable to open/read from %s" % cachefile)
  return env_dict


def capture_env_from_cmds(cmds, cachefile, errfile):
  """Capture the environment resulting from executing bash cmds."""
  # Emit small bash script to execute
  cmdfile = ".bashcmd"
  with open(cmdfile, "w") as wf:
    first = True
    for c in cmds:
      if first:
        first = False
        wf.write("%s 1> %s 2>&1\n" % (c, errfile))
      else:
        wf.write("%s 1>> %s 2>&1\n" % (c, errfile))
      wf.write("if [ $? != 0 ]; then\n")
      wf.write("  exit 1\n")
      wf.write("fi\n")
    wf.write("printenv > %s\n" % cachefile)
    wf.write("exit 0\n")
    wf.close()
    rc = u.docmdnf("bash %s" % cmdfile)
    if rc != 0:
      u.warning("bash cmd failed")
      u.warning("cmd script was:")
      u.docmd("cat %s" % cmdfile)
      u.warning("bash error output was:")
      u.docmd("cat %s" % errfile)
      raise Exception("command failed")


def simulate_lunch(abuild):
  """Simulate lunch command for specific target."""
  # If we have previously cached results, read them
  cachefile = ".lunch.%s.txt" % abuild
  errfile = ".basherr.%s.txt" % abuild
  if not os.path.exists(cachefile):
    cmds = [". build/envsetup.sh", "lunch %s" % abuild]
    capture_env_from_cmds(cmds, cachefile, errfile)
  lunched_env = read_env_cachefile(cachefile)
  load_environment(saved_env, lunched_env)
  # Sanity check
  apo = os.environ["ANDROID_PRODUCT_OUT"]
  if not apo:
    u.error("internal error -- no ANDROID_PRODUCT_OUT env setting")
  return lunched_env


def read_device_info():
  """Read info from environment about connected devices."""
  devtags = os.environ["DEVTAGS"]
  dtv = "'DEVTAGS' environment variable"
  if not devtags:
    u.warning("no setting for %s -- "
              "unable to flash to device(s)" % dtv)
    return False
  codenametotag = os.environ["CODENAMETOTAG"]
  cnv = "'CODENAMETOTAG' environment variable"
  if not devtags:
    u.warning("no setting for %s -- "
              "unable to flash to device(s)" % cnv)
    return False
  chunks = devtags.split()
  for chunk in chunks:
    pair = chunk.split(":")
    if len(pair) != 2:
      u.warning("malformed chunk %s in %s "
                "(skipping)" % (chunk, dtv))
      continue
    tag = pair[0]
    serial = pair[1]
    u.verbose(2, "tag %s serial %s" % (tag, serial))
    tag_to_serial[tag] = serial
  if not tag_to_serial:
    u.warning("malformed %s: no devices" % dtv)
    return False
  chunks = codenametotag.split()
  for chunk in chunks:
    pair = chunk.split(":")
    if len(pair) != 2:
      u.warning("malformed chunk %s in %s "
                "(skipping)" % (chunk, cnv))
      continue
    codename = pair[0]
    tag = pair[1]
    u.verbose(2, "codename %s tag %s" % (codename, tag))
    codename_to_tag[codename] = tag
  if not codename_to_tag:
    u.warning("malformed %s: no devices" % cnv)
    return False
  # Reading complete. Now match things up to make sure
  # that we have at least some correspondence.
  found_count = 0
  for codename, tag in codename_to_tag.iteritems():
    if tag not in tag_to_serial:
      u.warning("CODENAMETOTAG mentions tag %s, which "
                "does not appear in DEVTAGS" % tag)
    else:
      found_count += 1
  if found_count == 0:
    u.warning("no devices mentioned in CODENAMETOTAG "
              "are listed in DEVTAGS")
    return False
  return True


def get_device_tag_from_build(abuild):
  """Map build name (ex: aosp_hammerhead-userdebug) to tag (ex: N5)."""
  regex = re.compile(r"aosp_(\S+)\-\S+$")
  m = regex.match(abuild)
  if not m:
    u.warning("unable to flash build %s (can't derive "
              "device codename" % abuild)
    return None
  codename = m.group(1)
  if codename not in codename_to_tag:
    u.warning("unable to flash build %s (no entry in "
              "codename->tag mapping)" % abuild)
    return None
  tag = codename_to_tag[codename]
  return tag


def device_is_online(tag):
  """See if device online."""
  lines = u.docmdlines("showdevices.py")
  regex = re.compile(r"\s*(\S+)\s+(\S+)\s+(\S+)\s*$")
  for line in lines:
    m = regex.match(line)
    if not m:
      continue
    dtag = m.group(1)
    dserial = m.group(2)
    dstat = m.group(3)
    if dtag == tag and dstat == "device":
      u.verbose(1, "device %s online with serial %s" % (dtag, dserial))
      return dserial
  return None


def perform_flash(abuild):
  """Flash build to device if available."""
  # Determine device tag
  tag = get_device_tag_from_build(abuild)
  if not tag:
    return None
  # Device online?
  serial = device_is_online(tag)
  if not serial:
    u.warning("device '%s' is not online, can't flash" % tag)
    return None
  u.verbose(0, "waiting for device '%s'" % tag)
  docmd("adb -s %s wait-for-device" % serial)
  docmd("adb -s %s reboot bootloader" % serial)
  t1 = int(time.time())
  u.verbose(0, "flashing device '%s'" % tag)
  docmd("fastboot -s %s flashall" % serial)
  t2 = int(time.time())
  u.verbose(1, "took %d seconds to flash device '%s'" % (t2 - t1, tag))
  return serial


def collect_propval(propname, serial):
  """Collect value for a given system property."""
  lines = u.docmdlines("adb -s %s shell getprop" % serial)
  regex = re.compile(r"\[(\S+)\]\:\s+\[(.+)\]\s*$")
  for line in lines:
    m = regex.match(line)
    if m and m.group(1) == propname:
      return m.group(2)
  return None


def perform_verify(abuild, serial):
  """Verify flash for specific device."""

  # Step 1: wait for the device to become active on adb. Use a
  # one minute timeout for this first wait.
  t1 = int(time.time())
  rc = u.docmdwithtimeout("adb -s %s wait-for-device" % serial, 60)
  if rc == -1:
    u.verbose(0, "timeout while waiting for device after "
              "flashing build '%s'" % abuild)
    return
  t2 = int(time.time())
  delta = t2 - t1
  u.verbose(1, "adb wait-for-device took %d seconds" % delta)

  # Wait for the boot animation to complete. Allow three minutes here.
  for ii in range(20):
    u.verbose(1, "checking for boot animation iter %d" % ii)
    val = collect_propval("init.svc.bootanim", serial)
    if not val or val == "running":
      u.verbose(1, "boot animation still running, waiting...")
      if val:
        u.verbose(1, "returned value was %s" % val)
      time.sleep(10)
    else:
      u.verbose(1, "boot animation complete")
      break

  val = collect_propval("sys.boot_completed", serial)
  u.verbose(1, "sys.boot_completed is now '%s'" % val)

  # Ideas for this:
  # - adb wait-for-device
  # - adb logcat
  # - adb shell getprop
  # - check for sys.boot_completed from getprop
  # - compile and run java application


def summarize_dwarf(abuild):
  """Produce a report on dwarf producer."""
  apo = os.environ["ANDROID_PRODUCT_OUT"]
  if not apo:
    u.error("internal error -- no ANDROID_PRODUCT_OUT env setting")
  symsdir = "%s/symbols" % apo
  if os.path.exists(symsdir):
    lines = u.docmdlines("find %s -type f -print" % symsdir)
    slines = []
    for line in lines:
      slines.append(line.strip())
    if slines:
      outfile = "llvm-dwflavor-report.%s.txt" % abuild
      cmd = "llvm-dwflavor %s" % " ".join(slines)
      if flag_dryrun:
        u.verbose(1, "cmd: %s > %s" % (cmd, outfile))
      else:
        u.docmdout("llvm-dwflavor -show-comp-units "
                   "%s" % " ".join(slines), outfile, True)
  else:
    u.verbose(1, "DWARF flavor report stubbed "
              "out -- %s doesn't exist" % symsdir)


def perform_build(abuild):
  """Run a single specified build."""
  u.verbose(1, "running build: %s" % abuild)
  lunched_env = simulate_lunch(abuild)
  outfile = "build-err.%s.txt" % abuild
  cbf = "-t"
  if flag_checkbuild:
    cbf = "-T"
  if flag_mmma_target:
    bcmd = "mmm.py -k -j %d -a %s" % (flag_parfactor, flag_mmma_target)
  else:
    bcmd = "mmm.py -k -j %d %s" % (flag_parfactor, cbf)
  if flag_dryrun:
    bcmd = "echo %s" % bcmd
  rc = 0
  if flag_do_build:
    u.verbose(1, "kicking off build cmd %s for %s" % (bcmd, abuild))
    rc = u.docmderrout(bcmd, outfile, nf=True)
    result = "PASS"
    if rc != 0:
      result = "FAIL"
    u.verbose(0, "result for build '%s': %s" % (abuild, result))
    if rc != 0:
      u.verbose(0, ">> build log for failure: %s" % outfile)
    # Collect dwarf info
    summarize_dwarf(abuild)
  else:
    u.verbose(1, "not performing build (stubbed out)")
  if flag_do_clean:
    apo = os.environ["ANDROID_PRODUCT_OUT"]
    if not apo:
      u.error("internal error -- no ANDROID_PRODUCT_OUT env setting")
    u.verbose(1, "cleaning %s" % apo)
    if not flag_dryrun:
      shutil.rmtree(apo, ignore_errors=True)
    else:
      u.verbose(0, "rm -rf %s" % apo)
  else:
    u.verbose(1, "not performing post-build clean")
  # flash
  if rc == 0 and flag_do_flash:
    serial = perform_flash(abuild)
    if serial and flag_do_flashverify:
      perform_verify(abuild, serial)
  # restore env
  load_environment(lunched_env, saved_env)
  return rc


def perform():
  """Main driver routine."""
  save_environment()
  munge_makefiles_if_needed()
  if flag_targets:
    allbuilds = flag_targets
  else:
    builds = []
    for abuild, val in available_builds.iteritems():
      if val:
        builds.append(abuild)
    allbuilds = sorted(builds)
  passed = []
  failed = []
  for build_item in allbuilds:
    u.verbose(0, "starting build for '%s'" % build_item)
    rc = perform_build(build_item)
    if rc != 0:
      if flag_exit_on_err:
        u.verbose(0, "early exit due to build failure")
      failed.append(build_item)
    else:
      passed.append(build_item)
  print "Summary of results:"
  if passed:
    print "passed: %s" % " ".join(passed)
  if failed:
    print "failed: %s" % " ".join(failed)


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  mebase = os.path.basename(sys.argv[0])
  print """\
    usage:  %s [options]

    Available targets:
    %s

    options:
    -d     increase debug msg verbosity level
    -e     echo commands before executing
    -D     dry run: echo commands but do not execute
    -a X   invoke equivalent of 'mmma X' instead of full build
    -x     exit on first build failure
    -j N   set parallel build factor to N (default: 40)
    -S T   build for single target T or list of comma-separated targets
    -M     don't munge build/core/envsetup.mk to default to gcc before build
    -E     early exit after makefile munge (debugging)
    -C     perform checkbuild as opposed to regular build (compiles mores stuff)
    -Z     skip clean step after build
    -B     skip build step
    -F     flash each newly built image to a connected device,
           reading device info from DEVTAGS and CODENAMETOTAG
           environment variables
    -V     verify results of device flash (try to detect whether
           system has booted up correctly). This may take a while.

    Examples:

    1. build all targets

       %s

    2. build fugu, shamu targets, flash to device afterwards,
       use checkbuild

       %s -S aosp_fugu-userdebug,aosp_shamu-userdebug -F -C

    3. build fugu/shamu/flounder targets, skip makefile munging,
       use parallel factor of 20, echo commands

       %s -e -M -j 20 -S aosp_fugu-userdebug,aosp_shamu-userdebug,aosp_flounder-userdebug


    """ % (mebase, " ".join(sorted(available_builds.keys())),
           mebase, mebase, mebase)

  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_echo, flag_dryrun, flag_mmma_target, flag_parfactor
  global flag_exit_on_err, flag_do_flash, flag_do_build, flag_do_clean
  global flag_targets, flag_do_flashverify, flag_munge_make
  global flag_postmunge_exit, flag_checkbuild

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "da:j:xeDBCEFMVZS:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-e":
      flag_echo = True
    elif opt == "-a":
      if not os.path.exists(arg):
        usage("specified mmma target %s does not exist" % arg)
      u.verbose(1, "mmma target set to %s" % arg)
      flag_mmma_target = arg
    elif opt == "-j":
      flag_parfactor = int(arg)
    elif opt == "-S":
      if flag_targets:
        usage("supply single instance of -S option")
      tlist = arg.split(",")
      for t in tlist:
        if t not in available_builds:
          usage("specified target %s not in table "
                "of available builds" % t)
        else:
          available_builds[t] = 1
      flag_targets = tlist
    elif opt == "-x":
      flag_exit_on_err = True
    elif opt == "-B":
      flag_do_build = False
    elif opt == "-C":
      flag_checkbuild = True
    elif opt == "-Z":
      flag_do_clean = False
    elif opt == "-D":
      flag_dryrun = True
    elif opt == "-M":
      flag_munge_make = False
    elif opt == "-E":
      flag_postmunge_exit = True
    elif opt == "-V":
      flag_do_flashverify = True
    elif opt == "-F":
      if read_device_info():
        flag_do_flash = True

  if args:
    usage("unknown extra arguments")
  if flag_do_flashverify and not flag_do_flash:
    usage("use of -V option requires -F option.")
  if flag_postmunge_exit and not flag_munge_make:
    usage("can't use -E and -M options together")

  # Things set by 'lunch' should not be present in the environment
  abt = os.getenv("ANDROID_BUILD_TOP")
  if abt:
    u.error("ANDROID_BUILD_TOP already set "
            "(please don't run lunch before executing this cmd)")
  apo = os.getenv("ANDROID_PRODUCT_OUT")
  if apo:
    u.error("ANDROID_PRODUCT_OUT already set "
            "(please don't run lunch before executing this cmd)")
  aser = os.getenv("ANDROID_SERIAL")
  if aser:
    u.error("ANDROID_SERIAL already set "
            "(please don't select a device before executing this cmd)")


# ---------main portion of script -------------

u.setdeflanglocale()
parse_args()
perform()
