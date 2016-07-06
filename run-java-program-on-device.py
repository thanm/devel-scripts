#!/usr/bin/python
"""Compile and run specified Java file on connected device.

Compiles a specified java program, pushes it to the device,
and runs it on the device.

Notes:

 - first compilation will trigger the creation of a boot image,
   so expect it to take a while

"""

import getopt
import os
import re
import sys

import script_utils as u


# Device tag
whichdev = None

# Cmd file to run
cmdfile = None

# Cpu arch (ex: arm)
cpu_arch = None

# Cpu flavor
cpu_flav = 32

# Legal cpu archs
uname_to_cpu_arch = {"aarch64": ("arm", "arm64"),
                     "armv7l": ("arm", None),
                     "i686": ("x86", None)}

# Compile and run 64-bit
flag_64bit = False

# Java program to compile
flag_progname = None

# Basename of above
flag_progbase = None

# Native libs needed by app
flag_nativelibs = []

# Whether to run javac/dex
run_javac_and_dx = False

# Args to pass to program on run
flag_progargs = None

# Compile code with dex2oat on device before executing.
flag_dex2oat = True

# Echo commands before executing
flag_echo = False

# Echo commands before executing
flag_dryrun = False

# Run dalvikvm and/or dex2oat under strace
flag_strace = False

# Run dalvikvm under simpleperf
flag_simpleperf = False
flag_simpleperf_systemwide = False

# Use static simpleperf
flag_simpleperf_static = False

# Pull and symbolize OAT files from device
flag_symbolize = "none"

# Preserve temp files
flag_preserve = False

# Setting of $ANDROID_BUILD_TOP
abt = ""

# Setting of $ANDROID_PRODUCT_OUT
apo = ""

# Path to dx
dxpath = "dx"

# To track symbolization expansion stats
orig_oat_size = 0
symbolized_oat_size = 0


def docmd(cmd):
  """Execute a command."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmd(cmd)


def docmdout(cmd, outfile):
  """Execute a command."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + " > %s\n" % outfile)
  if flag_dryrun:
    return
  u.docmdout(cmd, outfile)


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


def emit_compile(wf, jarname):
  """Emit commands to perform compilation."""
  wrap_compile = ""
  if flag_strace:
    wrap_compile = "strace -f -o /data/local/tmp/compile-trace.txt "
  oatfile = ("/data/local/tmp/dalvik-cache"
             "/%s/data@local@tmp@%s@classes.dex"
             % (cpu_arch, jarname))
  wf.write("echo ... compiling\n")
  wf.write("%s/system/bin/dex2oat "
           "--generate-debug-info "
           "--compiler-filter=time "
           "--instruction-set=%s "
           "--dex-file=/data/local/tmp/%s "
           "--oat-file=%s "
           "--instruction-set=%s\n" %
           (wrap_compile, cpu_arch,
            jarname, oatfile, cpu_arch))
  wf.write("if [ $? != 0 ]; then\n")
  wf.write("  echo '** compile failed'\n")
  wf.write("  exit 1\n")
  wf.write("fi\n")


def emit_run(wf, jarname):
  """Emit command to invoke VM on jar."""
  intflag = ""
  wrap_run = ""
  if flag_strace:
    wrap_run = "strace -f -o /data/local/tmp/run-trace.txt "
  if flag_simpleperf:
    aarg = ""
    sp = "simpleperf"
    if flag_simpleperf_systemwide:
      aarg = "-a "
    if flag_simpleperf_static:
      sp = "./simpleperf_static"
    wrap_run = "%s record %s" % (sp, aarg)
  if not flag_dex2oat:
    intflag = "-Xint"
  wf.write("echo ... running\n")
  # wf.write("echo run stubbed out\n")
  # wf.write("exit 0\n")
  wf.write("%sdalvikvm%s %s -cp /data/local/tmp/%s -Xcompiler-option --generate-mini-debug-info"
           " %s\n" % (wrap_run, cpu_flav, intflag,
                      jarname, flag_progargs))
  wf.write("if [ $? != 0 ]; then\n")
  wf.write("  echo '** run failed'\n")
  wf.write("  exit 2\n")
  wf.write("fi\n")


def emit_cmds():
  """Emit commands to run into a small shell script."""
  global cmdfile
  try:
    cmdfile = "cmd-%d.sh" % os.getpid()
    jarname = "%s.jar" % flag_progbase
    with open(cmdfile, "a") as wf:
      if u.verbosity_level() > 0:
        wf.write("set -x\n")
      wf.write("cd /data/local/tmp\n")
      wf.write("export LD_LIBRARY_PATH=\n")
      wf.write("export ANDROID_DATA=/data/local/tmp\n")
      wf.write("export DEX_LOCATION=/data/local/tmp\n")
      wf.write("export ANDROID_ROOT=/system\n")
      wf.write("mkdir -p /data/local/tmp/dalvik-cache/%s\n" % cpu_arch)
      if flag_dex2oat:
        emit_compile(wf, jarname)
      emit_run(wf, jarname)
      wf.write("exit 0\n")
  except IOError:
    u.error("unable to open/write to %s" % cmdfile)
  u.verbose(1, "cmd file %s emitted" % cmdfile)
  docmd("adb push %s /data/local/tmp" % cmdfile)


def collect_file_size(afile):
  """Collect file size in bytes."""
  if flag_dryrun:
    return 1
  try:
    fsiz = os.path.getsize(afile)
  except os.error as oe:
    u.error("unable to collect file size for %s: %s" % (afile, oe))
  return fsiz


def symbolize_file(oatfile, uncond):
  """Symbolize compiled OAT files."""
  global orig_oat_size, symbolized_oat_size
  symfs = os.path.join(apo, "symbols")
  symoat = os.path.join(symfs, oatfile[1:])
  symoatdir = os.path.dirname(symoat)
  u.verbose(1, "considering %s" % symoat)
  if uncond or not os.path.exists(symoat):
    docmd("mkdir -p %s" % symoatdir)
    docmd("adb pull %s %s" % (oatfile, symoat))
    docmd("rm -f symbolized.oat")
    origsize = collect_file_size(symoat)
    orig_oat_size += origsize
    docmd("oatdump --symbolize=%s" % symoat)
    newsize = collect_file_size("symbolized.oat")
    symbolized_oat_size += newsize
    docmd("mv -f symbolized.oat %s" % symoat)
    delta = newsize - origsize
    if delta:
      frac = 100.0 * (1.0 * delta) / (1.0 * origsize)
      u.verbose(1, "%s expanded %d bytes %f percent "
                "from symbolization" % (symoat, delta, frac))


def collect_files_to_symbolize(location):
  """Generate list of OAT files to symbolize."""
  # This will hoover up everything, including things we don't want
  # to look at (ex: boot.art)
  lines = u.docmdlines("adb shell find %s -type f -print" % location)
  files = []
  regex = re.compile(r"^.+@boot\.art$")
  for line in lines:
    afile = line.strip()
    if regex.match(afile):
      continue
    files.append(afile)
  return files


def perform_symbolization():
  """Symbolize compiled OAT files."""
  if flag_symbolize == "none":
    return
  jarname = "%s.jar" % flag_progbase
  oatfile = ("/data/local/tmp/dalvik-cache"
             "/%s/data@local@tmp@%s@classes.dex"
             % (cpu_arch, jarname))
  symbolize_file(oatfile, True)
  if flag_symbolize != "all":
    return
  locations = ["/data/local/tmp/dalvik-cache",
               "/data/dalvik-cache/%s" % cpu_arch]
  for loc in locations:
    files = collect_files_to_symbolize(loc)
    for f in files:
      symbolize_file(f, False)


def perform():
  """Main driver routine."""
  if run_javac_and_dx:
    docmd("javac -g -source 1.7 -target 1.7 %s" % flag_progname)
    docmd("%s -JXmx256m --debug --dex "
          "--output=classes.dex %s.class" % (dxpath, flag_progbase))
    doscmd("zip %s.jar classes.dex" % flag_progbase)
  doscmd("adb push %s.jar /data/local/tmp" % flag_progbase)
  if flag_nativelibs:
    for lib in flag_nativelibs:
      doscmd("adb push %s /data/local/tmp" % lib)
  if flag_simpleperf_static:
    doscmd("adb push %s/system/bin/simpleperf_static /data/local/tmp" % apo)
  emit_cmds()
  if flag_dryrun:
    u.verbose(0, "contents of cmd file:")
    u.docmd("cat %s" % cmdfile)
  rc = docmdnf("adb shell sh /data/local/tmp/%s" % cmdfile)
  if rc != 0:
    u.error("** command failed: adb shell sh "
            "/data/local/tmp/%s (temp file left in .)" % cmdfile)
  else:
    if flag_preserve:
      u.verbose(0, "cmd files preserved: %s on "
                "host and /data/local/tmp/%s on target"
                % (cmdfile, cmdfile))
    else:
      u.docmd("rm -f %s" % cmdfile)
      docmd("adb shell rm -f /data/local/tmp/%s" % cmdfile)
  if flag_strace:
    docmd("adb pull /data/local/tmp/run-trace.txt .")
    if flag_dex2oat:
      docmd("adb pull /data/local/tmp/compile-trace.txt .")
  if flag_simpleperf:
    docmd("adb pull /data/local/tmp/perf.data .")
  perform_symbolization()
  if flag_simpleperf:
    docmdout("simpleperf report --symfs %s/symbols" % apo, "report.txt")


def wrapup():
  """Emit stats."""
  if symbolized_oat_size:
    delta = symbolized_oat_size - orig_oat_size
    if delta:
      frac = 100.0 * (1.0 * delta) / (1.0 * orig_oat_size)
      u.verbose(0, "total expansion of %d bytes %f percent "
                "from symbolization" % (delta, frac))


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
    meb = os.path.basename(sys.argv[0])
  print """\
    usage:  %s [options] program.java <args>

    options:
    -d     increase debug msg verbosity level
    -p     preserve tempfiles
    -e     echo commands before executing
    -X     run dex2oat and/or dalvikvm under strace
    -P     run dalvikvm under simpleperf
    -A     run dalvikvm under simpleperf in system-wide mode
    -Q     use simpleperf_static
    -I     interpret program instead of compiling with dex2oat
    -R     rerun existing compiled file only
    -W     compile and run 64-bit
    -j X   application uses native library X
    -s S   set ANDROID_SERIAL to S
    -S X   pull and symbolize (with oatdump) compiled OAT files,
           where X is 'all' (pull and symbolize all cached OAT files),
           'single' (pull and symbolize only the single compiled OAT),
           or 'none' (the default -- no symbolization)
    -D     dry run: echo commands but do not execute

Examples:

  1. Compile and run fibonacci.java in 32-bit mode,
     invoking class 'fibonacci' with args '19 19 19'

    %s fibonacci.java fibonacci 19 19 19

  2. Compile and run fibonacci.java in 64-bit mode

    %s -W -e fibonacci.java fibonacci 3 3 3

  3. Compile and run fibonacci.java in 32-bit mode,
     invoking compiler and VM using 'strace', then upload
     resulting traces:

    %s -X -e fibonacci.java fibonacci

  4. Compile and run fibonacci.java in 32-bit mode,
     execute run with 'simpleperf', upload and symbolize
     resulting OAT file, and pull perf.data from device

    %s -S single -P -e \
           fibonacci.java fibonacci 39 39 39

    """ % (meb, meb, meb, meb, meb)
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_progargs, flag_progname, flag_progbase
  global flag_echo, flag_dryrun, flag_strace, flag_dex2oat, flag_64bit
  global cpu_flav, flag_simpleperf, flag_symbolize, flag_preserve
  global flag_simpleperf_systemwide, run_javac_and_dx, flag_simpleperf_static

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "depAQDIPS:s:j:WX")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-e":
      flag_echo = True
    elif opt == "-p":
      flag_preserve = True
    elif opt == "-X":
      flag_strace = True
    elif opt == "-Q":
      flag_simpleperf = True
      flag_simpleperf_static = True
    elif opt == "-S":
      if arg != "all" and arg != "single" and arg != "none":
        usage("invalid argument for -S option (must "
              "be: 'all', 'single', or 'none')")
      flag_symbolize = arg
    elif opt == "-j":
      if not os.path.exists(arg):
        usage("unable to access native lib %s" % arg)
      u.verbose(1, "adding native lib %s" % arg)
      flag_nativelibs.append(arg)
    elif opt == "-s":
      os.putenv("ANDROID_SERIAL", arg)
      os.environ["ANDROID_SERIAL"] = arg
    elif opt == "-P":
      flag_simpleperf = True
    elif opt == "-A":
      flag_simpleperf = True
      flag_simpleperf_systemwide = True
    elif opt == "-I":
      flag_dex2oat = False
    elif opt == "-W":
      cpu_flav = "64"
      flag_64bit = True
    elif opt == "-D":
      flag_dryrun = True

  if not args:
    usage("supply name of java program to run as first arg")
  flag_progname = args[0]
  if not os.path.exists(flag_progname):
    u.error("unable to access java program %s" % flag_progname)
  regex1 = re.compile(r"^(\S+)\.java$")
  regex2 = re.compile(r"^(\S+)\.jar$")
  m1 = regex1.match(flag_progname)
  m2 = regex2.match(flag_progname)
  if m1:
    run_javac_and_dx = True
    flag_progbase = m1.group(1)
  elif m2:
    run_javac_and_dx = False
    flag_progbase = m2.group(1)
  else:
    usage("specified program must end with .java or .jar")

  pargs = args[1:]
  if not pargs:
    u.error("supply at least one arg (class name)")
  flag_progargs = " ".join(pargs)
  u.verbose(1, "javaprog: %s" % flag_progname)
  u.verbose(1, "args: %s" % flag_progargs)

  if flag_simpleperf and flag_strace:
    usage("supply at most one of -P / -X options")


def setup():
  """Perform assorted setups prior to main part of run."""
  global abt, apo, whichdev, cpu_arch, dxpath

  # Check to make sure we can run adb, etc
  u.doscmd("which adb")
  rc = u.docmdnf("which dx")
  if rc != 0:
    u.doscmd("which prebuilts/sdk/tools/dx")
    dxpath = "prebuilts/sdk/tools/dx"
  u.doscmd("which javac")

  # Collect device flavor
  lines = u.docmdlines("whichdevice.sh")
  if len(lines) != 1:
    u.error("unexpected output from whichdevice.sh")
  whichdev = lines[0].strip()
  u.verbose(1, "device: %s" % whichdev)

  bitness = 32
  cpu_tup_idx = 0
  if flag_64bit:
    bitness = 64
    cpu_tup_idx = 1

  # Figure out what architecture we're working with,
  # and make sure it supports the requested mode (32 or 64 bit)
  output = u.docmdlines("adb shell uname -m")
  tag = output[0].strip()
  if tag not in uname_to_cpu_arch:
    u.error("internal error: unsupported output %s from "
            "from uname -m -- please update script" % tag)
  tup = uname_to_cpu_arch[tag]
  cpu_arch = tup[cpu_tup_idx]
  if not cpu_arch:
    u.error("%d-bit support not available on "
            "this arch (uname -m: %s)" % (bitness, tag))

  # Did we run lunch?
  abt = os.getenv("ANDROID_BUILD_TOP")
  if abt is None:
    u.error("ANDROID_BUILD_TOP not set (did you run lunch?)")
  apo = os.getenv("ANDROID_PRODUCT_OUT")
  if apo is None:
    u.error("ANDROID_PRODUCT_OUT not set (did you run lunch?)")
  u.verbose(1, "ANDROID_PRODUCT_OUT: %s" % apo)


# ---------main portion of script -------------

u.setdeflanglocale()
parse_args()
setup()
perform()
wrapup()
