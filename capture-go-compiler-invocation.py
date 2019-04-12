#!/usr/bin/python3
"""Extracts compile commands from go build output.

Reads either stdin or a specified input file, then post-processes to identify
go/gccgo compiler invocations. Output is post-processed to create a script that
can be invoked to rerun the compile, or optionally is examined to select out the
gccgo compiler invocation. Useful for doing compiler reruns and re-invocations
under the debugger.

"""

import getopt
import hashlib
import os
import re
import shlex
import subprocess
import sys

import script_utils as u

# Extract single cmd vs all cmds
flag_single = False

# Input and output file (if not specified, defaults to stdin/stdout)
flag_infile = None
flag_outfile = None

# place to which work dir should be relocated
flag_relocate = None

# Set up for gccgo debugging compilation of specified go src file
flag_gccgo_gdb = None

# Set to true to emit cpuprofile code
flag_cpuprofile = False

# Set to true to emit Auto-FDO collection code
flag_autofdoprofile = False

# Path to 'perf' to use for with auto-FDO collection
flag_perfbin = "perf"

# Emit "-c 1" to compile commands to disable parallel backend
flag_nopar = False

# Emit "setarch x86_64 -R" to compile commands to disable ASLR.
flag_noaslr = False

# Emit loop of N iterations around entire compile sequence.
flag_emitloop = False

# Captures first gccgo compilation line
gccgo_invocation = None
gccgo_location = None

# workdir
workdir = None

# Drivers we encounter while scanning the build output
drivers = {}
driver_count = 0

# Driver flavor (indexed by driver var). Key is one of: "gc", "gccgo", "gollvm"
driver_flavor = {}


def mktempname(salt, instance):
  """Create /tmp file name for compile output."""
  m = hashlib.md5()
  m.update(salt)
  hd = m.hexdigest()
  return "/tmp/%s.%d.err.txt" % (hd, instance)


def extract_line(outf, driver, driver_var, argstring, curdir):
  """Post-process a line."""
  global gccgo_invocation, gccgo_location
  # Now filter the args.
  args = []
  regparen = re.compile(r"^\-Wl,\-[\(\)]$")
  regsrc = re.compile(r"^(\S+)\.go$")
  regpar = re.compile(r"^\-c=\d+$")
  raw_args = shlex.split(argstring)
  numraw = len(raw_args)
  gosrcfiles = {}
  srcfiles = []
  for idx in range(0, numraw):
    arg = raw_args[idx]
    if regpar.match(arg):
      continue
    mp = regparen.match(arg)
    if mp:
      arg = "'%s'" % arg
    if regsrc.match(arg):
      gosrcfiles[arg] = 1
      srcfiles.append(arg)
    if not arg:
      arg = "\"\""
    args.append(arg)

  cparg = ""
  preamble = ""
  outf.write("parg=""\n")
  outf.write("pwrap=""\n")
  if driver_flavor[driver_var] != "gc":
    outf.write("PRELOAD=""\n")
  outf.write("pcount=`expr $pcount + 1`\n")
  if flag_cpuprofile:
    outf.write("if [ \"$CPUPROFILE\" != \"\" ]; then\n")
    if driver_flavor[driver_var] == "gc":
      outf.write("  parg=-cpuprofile=$CPUPROFILE/p${pcount}.p\n")
    else:
      outf.write("  export PROFDEST=$CPUPROFILE/p${pcount}.p\n")
      outf.write("  PRELOAD=/usr/lib/libprofiler.so.0 \n")
      preamble = "CPUPROFILE=$PROFDEST LD_PRELOAD=${PRELOAD} "
    outf.write("fi\n")
    cparg = " $parg"
  if flag_autofdoprofile:
    outf.write("if [ \"$AUTOFDOPROFILE\" != \"\" ]; then\n")
    outf.write("  pwrap=\"%s record -e cycles -c 100000 -b -o "
               "$AUTOFDOPROFILE/perf.data.${pcount}\"\n" % flag_perfbin)
    outf.write("fi\n")
  nparg = ""
  if flag_nopar:
    nparg = " -c 1"
  noaslr = "setarch x86_64 -R"
  if flag_noaslr:
    noaslr = ""
  outf.write("%s%s ${pwrap} ${%s} "
             "%s %s $* %s \n" % (preamble, noaslr, driver_var, cparg,
                                 nparg, " ".join(args)))
  if gosrcfiles:
    u.verbose(0, "extracted compile cmd for: %s" % " ".join(srcfiles))
  if flag_gccgo_gdb and flag_gccgo_gdb in gosrcfiles:
    u.verbose(0, "found gccgo compilation line "
              "including %s" % flag_gccgo_gdb)
    gccgo_invocation = []
    gccgo_invocation.append(driver)
    gccgo_invocation.extend(args)
    gccgo_location = curdir
  outf.write("if [ $? != 0 ]; then\n")
  outf.write("  echo 'error: %s compilation failed'\n" % " ".join(srcfiles))
  outf.write("  exit 1\n")
  outf.write("fi\n")

  if flag_single:
    return -1
  return 1


def perform_extract(inf, outf):
  """Read inf and extract compile cmd to outf."""
  global driver_count, workdir

  regwrk = re.compile(r"^WORK=(\S+)$")
  reggcg = re.compile(r"^(\S+/bin/gccgo)\s+(.+)$")
  regglm = re.compile(r"^(\S+/bin/llvm-goc)\s+(.+)$")
  reggc = re.compile(r"^(\S+/compile)\s+(.+)$")
  regcd = re.compile(r"^cd (\S+)\s*$")
  regar = re.compile(r"^ar .+$")
  regcp = re.compile(r"^cp (\S+) (\S+)$")
  regmkdir = re.compile(r"^mkdir .+$")
  regcat = re.compile(r"^cat >\$WORK.*$")
  regeof = re.compile(r"^EOF\s*$")

  outf.write("#!/bin/sh\n")
  outf.write("# [this file auto-generated via the command:]\n")
  outf.write("# %s\n" % " ".join(sys.argv))
  if flag_cpuprofile:
    outf.write("pcount=0\n")
  if flag_emitloop:
    outf.write("ITER=0\n")
    outf.write("if [ -z $LOOP_LIMIT ]; then\n")
    outf.write("  LOOP_LIMIT=1\n")
    outf.write("fi\n")
    outf.write("while [ $ITER -lt $LOOP_LIMIT ];\ndo\n")
    outf.write("ITER=`expr $ITER + 1`\n")

  cdir = "."
  while True:
    line = inf.readline()
    if not line:
      break
    dflavor = ""
    u.verbose(2, "line is %s" % line.strip())
    mwrk = regwrk.match(line)
    if mwrk:
      workdir = mwrk.group(1)
      if flag_relocate:
        u.verbose(0, "... relocating work dir %s to "
                  "%s" % (workdir, flag_relocate))
        if os.path.exists(flag_relocate):
          u.docmd("rm -rf %s" % flag_relocate)
        u.docmd("cp -r %s %s" % (workdir, flag_relocate))
        outf.write("WORK=%s\n" % flag_relocate)
      else:
        outf.write(line)
      continue
    mcd = regcd.match(line)
    if mcd:
      cdir = mcd.group(1)
      outf.write("cd %s\n" % cdir)
      continue
    mmkdir = regmkdir.match(line)
    if mmkdir:
      outf.write(line)
      continue
    mcat = regcat.match(line)
    if mcat:
      while True:
        line = inf.readline()
        if not line:
          u.error("fatal: end of file while looking for EOF tag")
        u.verbose(2, "line is %s" % line.strip())
        meof = regeof.match(line)
        if meof:
          u.verbose(2, "seen EOF ==")
          break
      continue
    mar = regar.match(line)
    if mar:
      outf.write(line)
      continue
    mcp = regcp.match(line)
    if mcp:
      outf.write(line)
      continue
    mgc = reggc.match(line)
    mgcg = reggcg.match(line)
    mgcglm = regglm.match(line)
    if not mgc and not mgcg and not mgcglm:
      continue
    if mgc:
      driver = mgc.group(1)
      dflavor = "gc"
      argstring = mgc.group(2)
    elif mgcglm:
      driver = mgcglm.group(1)
      dflavor = "gollvm"
      argstring = mgcglm.group(2)
    else:
      driver = mgcg.group(1)
      dflavor = "gccgo"
      argstring = mgcg.group(2)

    u.verbose(1, "matched: %s %s" % (driver, argstring))

    driver_var = "DRIVER%d" % driver_count
    if driver in drivers:
      driver_var = drivers[driver]
    else:
      outf.write("%s=%s\n" % (driver_var, driver))
      drivers[driver] = driver_var
      driver_flavor[driver_var] = dflavor
      driver_count += 1
    if extract_line(outf, driver, driver_var, argstring, cdir) < 0:
      break
  if flag_emitloop:
    outf.write("done\n")


def setup_gccgo_gdb():
  """Set up for gccgo debugging."""
  if not gccgo_location:
    u.warning("failed to locate gccgo compilation "
              "of %s" % flag_gccgo_gdb)
    return
  outfile = ".gccgo.err.txt"
  here = os.getcwd()
  gloc = gccgo_location
  if here != gloc:
    u.warning("gccgo compile takes place in %s, "
              "not here (%s)" % (gccgo_location, here))
    regloc = re.compile(r"\$WORK/(\S+)$")
    m = regloc.match(gccgo_location)
    if m:
      if flag_relocate:
        gloc = os.path.join(flag_relocate, m.group(1))
      else:
        gloc = os.path.join(workdir, m.group(1))

      u.verbose(1, "revised gloc dir is %s" % gloc)
  os.chdir(gloc)
  driver = gccgo_invocation[0]
  args = gccgo_invocation[1:]
  for idx in range(0, len(args)):
    if args[idx] == "$WORK":
      if flag_relocate:
        args[idx] = flag_relocate
      else:
        args[idx] = workdir
  cmd = ("%s -v %s" % (driver, " ".join(args)))
  u.verbose(1, "in %s, executing gdb setup cmd: %s" % (os.getcwd(), cmd))
  rc = u.docmderrout(cmd, outfile, True)
  if rc != 0:
    u.warning("cmd failed: %s" % cmd)
  try:
    inf = open(outfile, "rb")
  except IOError as e:
    u.error("internal error: unable to consume tmp "
            "file %s? error %s" % (outfile, e.strerror))
  lines = inf.readlines()
  inf.close()
  found = False
  reg1 = re.compile(r"^\s*(\S+/go1)\s+(\S.+)$")
  for line in lines:
    u.verbose(2, "gccgo -v line is %s" % line.strip())
    m = reg1.match(line)
    if m:
      go1exe = m.group(1)
      u.verbose(1, "go1 driver is %s" % go1exe)
      go1args = m.group(2)
      u.verbose(1, "go1 args: %s" % go1args)
      # Create symlink
      if not os.path.exists("go1"):
        u.verbose(0, "symlinking to %s" % go1exe)
        os.symlink(go1exe, "go1")
      # Dump args
      u.verbose(0, "writing args to .gdbinit")
      try:
        outf = open(".gdbinit", "w")
      except IOError as e:
        u.error("unable to open %s: "
                "%s" % (".gdbinit", e.strerror))
      outf.write("# gud-gdb --fullname ./go1\n")
      outf.write("set args %s" % go1args)
      outf.close()
      u.verbose(0, "starting emacs")
      subprocess.Popen(["emacs", ".gdbinit"])
      return
  if not found:
    u.error("unable to locate go1 invocation in gccgo -v output")
  os.chdir(here)


def perform():
  """Main driver routine."""
  inf = sys.stdin
  outf = sys.stdout
  if flag_infile:
    try:
      inf = open(flag_infile, "r")
    except IOError as e:
      u.error("unable to open input file %s: "
              "%s" % (flag_infile, e.strerror))
  if flag_outfile:
    try:
      outf = open(flag_outfile, "w")
    except IOError as e:
      u.error("unable to open output file %s: "
              "%s" % (flag_outfile, e.strerror))
  perform_extract(inf, outf)
  if flag_infile:
    inf.close()
  if flag_outfile:
    outf.close()
  if flag_gccgo_gdb:
    setup_gccgo_gdb()


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options] < input > output

    options:
    -d    increase debug msg verbosity level
    -i F  read from input file F (presumably captured 'go build' output)
    -o G  write compile script to file G
    -R X  relocate WORK directory to local dir X (overwrites X)
    -G Y  set up for gccgo debugging for source file 'Y'; reruns compile
          with -v to capture args and emits .gdbinit, etc.
    -C    augment output script with -cpuprofile cmds (set CPUPROFILE
          to tgt dir prior to executing script)
    -A    augment output script to collect perf.data files for
          each run (set AUTOFDOPROFILE to tgt dir prior to script execution)
    -P X  path to 'perf' binary is X
          to tgt dir prior to executing script)
    -N    add "-c 1" to all compile commands captured
    -Z    prefix compile commands with setarch to disable ASLR.
    -L    emit a loop of $LOOP_LIMIT iterations around entire compile.

    Examples:

    1. Post-process compile transcript 'trans.txt' to produce
       compilation script 'comp.sh', relocating work dir to 'work'

       go test -x -work -c -a -compiler gccgo . &> trans.txt
       %s -i trans.txt -o comp.sh -R ./work

    2. Post-process go build output file 'gobuild.txt' to set up
       for debugging gccgo when compiling blah.go

       %s -i gobuild.txt -G blah.go


    """ % (me, me, me))
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_infile, flag_outfile, flag_single
  global flag_gccgo_gdb, flag_relocate, flag_cpuprofile, flag_nopar
  global flag_autofdoprofile, flag_perfbin, flag_noaslr, flag_emitloop

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "di:o:R:G:CASZNP:L")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  if args:
    usage("extra unknown arguments")
  for opt, arg in optlist:
    u.verbose(1, "++ examining opt %s arg %s" %  (opt, arg))
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-S":
      flag_single = True
    elif opt == "-G":
      flag_gccgo_gdb = arg
    elif opt == "-Z":
      flag_noaslr = arg
    elif opt == "-C":
      flag_cpuprofile = True
    elif opt == "-A":
      flag_autofdoprofile = True
    elif opt == "-N":
      flag_nopar = True
    elif opt == "-P":
      flag_perfbin = arg
    elif opt == "-L":
      flag_emitloop = True
    elif opt == "-R":
      flag_relocate = arg
      if flag_relocate[0] != "/":
        flag_relocate = os.path.join(os.getcwd(), flag_relocate)
    elif opt == "-i":
      if flag_infile:
        usage("supply at most one -i option")
      flag_infile = arg
    elif opt == "-o":
      if flag_outfile:
        usage("supply at most one -o option")
      flag_outfile = arg


# Setup
u.setdeflanglocale()
parse_args()
perform()
