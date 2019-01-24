#!/usr/bin/python
"""Script to benchmark gc <-> gccgo.

This script uses the Go compiler itself as a benchmark to compare how
Go programs perform when built with gccgo vs the main gc.  It
downloads a copy of the Go git repo in the process and builds the
compiler executable with gccgo and with the main go compiler.

Once the executable under test ("compile") is built in the proper way,
then script then uses that compiler to compile itself -- this
generates a series of executions which it then replays (these runs are
the things being benchmarked) -- this capturing is performed by the helper
script 'capture-go-compiler-invocation.py'. We collect wall clock time, metrics
from perf "stat", a perf.data file from "perf record" for each
flavor, and pprof cpu profiles.

Output files are:

  err.bootstrap.<flavor>.txt

           output of building "compile" where <flavor> is either
           'gccgo', 'gollvm', or 'gc'

  err.benchrun.bootstrap.<flavor>.<tag>.txt

           output of a single benchmark run where <flavor> is
           'gccgo'/'gollvm'/'gc' and <tag> corresponds to what we're
           measuring ("tim" for wall block time, "perfdata" for
           perf.data collection run, etc)

  rep.<flavor>.txt

           output of 'perf report' run on perf.data collected from
           benchmark run; <flavor> is 'gccgo'/'gollvm'/'gc'

  ann<K>.<flavor>.txt

           output of 'perf annotate' run on perf.data collected from
           benchmark run; <flavor> is 'gccgo'/'gollvm'/'gc', and <K>
           is index of function of interest

  pprofdis<K>.<flavor>.txt

           output of 'pprof disasm' run on perf.data collected from
           benchmark run; <flavor> is 'gccgo'/'gollvm'/'gc', and <K>
           is index of function of interest

  asm<K>.<flavor>.txt

           output of 'objdump -dl' on compiler executable used for
           benchmark run; <flavor> is 'gccgo'/'gollvm'/'gc', and <K>
           is index of function of interest

Scripts generated along the way:

  build.bootstrap.<flavor>.sh

       This does a make.bash build in "bootstrap.<flavor>" with
       GOROOT_BOOTSTRAP set appropriately. This is to generate the
       "compile" binaries that we want to benchmark.

  prep.bootstrap.<flavor>.sh

       Perform a preparatory build of the go compiler in
       "bootstrap.<flavor>" using the binary we want to
       benchmark. This insures that the compiler dependencies are
       built and captures each of the "compile" invocations actually
       executed into a script "runbench.bootstrap.<flavor>.sh".

  runbench.bootstrap.<flavor>.sh

       This script contains a replay of the "compile" executions that
       happen during a "go build" of the compiler. The intent here is
       to capture just the 'compile' actions during a 'go build'
       session (stripping out assembling, copying libraries, etc).

  bench.bootstrap.<flavor>.<tag>.sh

       Wrapper for executing the "runbench" script (runs the runbench
       script either with "/bin/time" or with "perf record to capture
       performance data of interest.

"""

import getopt
import os
import re
import shutil
import sys
import tempfile

import script_utils as u


# Echo command before executing
flag_echo = True

# Dry run mode
flag_dryrun = False

# Keep work dirs
flag_keepwork = False

# Skip bootstrap if bootstrap dirs already present
flag_skip_bootstrap = False

# Skip benchmark run
flag_skip_benchrun = False

# Generate HTML versions of reports
flag_genhtml = False

# Include linux perf runs
flag_doperf = False

# Alternate run tag (useful mainly with -O)
flag_othertag = None

# Auto-FDO input profile file for this fun
flag_autofdoprofile = None

# Include pprof profiling runs
flag_dopprof = True

# Include AutoFDO perf.data collection runs
flag_collect_autofdo_perf = False

# Where to get go
go_git = "https://go.googlesource.com/go"

# Where to look for gc-based go installation
go_install = None

# Where to look for gccgo-based go installation
gccgo_install = None

# Where to look for gollvm-based go installation
gollvm_install = None

# Hard-coded list of functions to analyze more closely
interesting_funcs = [("runtime.scanobject",
                      "runtime.scanobject"),
                     ("runtime.mallocgc",
                      "runtime.mallocgc"),
                     ("runtime.heapBits.next",
                      "runtime.heapBits.next"),
                     ("runtime.heapBitsSetType",
                      "runtime.heapBitsSetType"),
                     ("bootstrap/cmd/compile/internal/ssa.applyRewrite",
                      "bootstrap..z2fcmd..z2fcompile.."
                      "z2finternal..z2fssa.applyRewrite")]

# If filled in, then set GOMAXPROCS to this value
flag_gomaxprocs = None

# Which version of perf to run
flag_perf = "perf"

# Count of lines in ppo file
ppolines = 0

# Files we generate
generated_reports = {}

# Variants/flavors that we're benchmarking

gc_variant = {
    "tag": "gc",
    "order": 0,
    "install": None,
    "extra_flags": None
    }

gccgo_variant = {
    "tag": "gccgo",
    "order": 1,
    "install": None,
    "extra_flags": "-O2 -static"
    }

gollvm_variant = {
    "tag": "gollvm",
    "order": 2,
    "install": None,
    "extra_flags": "-O2 -static"
    }

gollvm3_variant = {
    "tag": "gollvm",
    "derived": "gollvm",
    "order": 3,
    "install": None,
    "extra_flags": "-O3 -static"
    }

# "gollvm3": gollvm3_variant,

variants = {
    "gc": gc_variant,
    "gccgo": gccgo_variant,
    "gollvm": gollvm_variant,
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


def docmderrout(cmd, outfile):
  """Execute a command."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmderrout(cmd, outfile)


def docmdout(cmd, outfile):
  """Execute a command to an output file."""
  if flag_echo:
    sys.stderr.write("executing: " + cmd + "\n")
  if flag_dryrun:
    return
  u.docmdout(cmd, outfile)


def copydir(src, dst):
  """Copy directory."""
  if flag_echo:
    sys.stderr.write("copying dir %s to dir %s\n" % (src, dst))
  if flag_dryrun:
    return
  shutil.copytree(src, dst)


def rmdir(src):
  """Remove directory."""
  if flag_echo:
    sys.stderr.write("removing dir %s\n" % src)
  if flag_dryrun:
    return
  shutil.rmtree(src)


def rmfile(afile):
  """Remove a file."""
  if flag_echo:
    sys.stderr.write("removing file %s\n" % afile)
  if flag_dryrun:
    return
  os.unlink(afile)


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


def dormdir(thedir):
  """Remove dir."""
  if flag_echo:
    sys.stderr.write("rm -r " + thedir + "\n")
  if flag_dryrun:
    return
  if not os.path.exists(thedir):
    return
  try:
    rmdir(thedir)
  except OSError as err:
    u.error("rmdir(%s) failed: %s" % (thedir, err))


def patch_repo(repo, flags):
  """Patch go repo if needed."""
  rc = u.docmdnf("grep -q gccgoflags %s/src/cmd/dist/buildtool.go" % repo)
  if rc == 0:
    u.verbose(1, "src/cmd/dist/buildtool.go already patched")
    return
  # Remove any version file if it exists.
  vfile = os.path.join(repo, "VERSION")
  if not os.path.exists("go.repo"):
    rmfile(vfile)
  # Mangle build flags.
  regex = re.compile(r"^.+gcflags=.+$")
  oldf = "%s/src/cmd/dist/buildtool.go" % repo
  newf = "%s/src/cmd/dist/buildtool.go.patched" % repo
  try:
    with open(newf, "w") as wf:
      try:
        with open(oldf, "r") as rf:
          lines = rf.readlines()
          for line in lines:
            if regex.match(line):
              comps = line.split()
              newcomps = []
              for c in comps:
                if c == "\"-gcflags=-l\",":
                  u.verbose(0, "patching gcflags line\n")
                  newcomps.append("\"-gccgoflags=%s\", " % flags)
                  newcomps.append("\"-p=8\", ")
                newcomps.append(c)
              line = " ".join(newcomps)
              line += "\n"
            wf.write(line)
      except IOError:
        u.verbose(2, "open failed for %s" % oldf)
  except IOError:
    u.verbose(2, "open failed for %s" % newf)
  docmd("mv %s %s" % (newf, oldf))


def repo_setup():
  """Set up repos for bench run."""
  # Download a copy of go repo if not already present
  if not os.path.exists("go.repo"):
    u.verbose(0, "... no go repo found, cloning")
    doscmd("git clone %s go.repo" % go_git)
  # Make copies
  u.verbose(0, "... refreshing repo copies")
  ordered = order_variants()
  for v in ordered:
    if not variants[v]["install"]:
      u.verbose(0, "... no installation for variant %s, skipping" % v)
    else:
      c = "bootstrap.%s" % v
      if os.path.exists(c):
        if flag_skip_bootstrap:
          u.verbose(0, "... bootstrap dir %s exists, will reuse" % c)
          continue
        rmdir(c)
      u.verbose(0, "copying go.repo into %s" % c)
      copydir("go.repo", c)
      if v != "gc":
        # Patch repo to insure that gccgo build is with -O2 or -O3
        patch_repo(c, variants[v]["extra_flags"])


def zversion_gen():
  """Create dummy zversion.go file in gccgo root."""
  sidir = os.path.join(gccgo_install, "src/runtime/internal/sys")
  docmd("mkdir -p %s" % sidir)
  if flag_dryrun:
    u.verbose(0, "<generate %s/zversion.go>" % sidir)
    return
  zgo = os.path.join(sidir, "zversion.go")
  if os.path.exists(zgo):
    rmfile(zgo)
  u.verbose(1, "manufacturing dummy %s" % zgo)
  try:
    with open(zgo, "w") as wf:
      me = os.path.basename(sys.argv[0])
      wf.write("// auto generated by %s\n\n" % me)
      wf.write("package sys\n\n")
      wf.write("const DefaultGoroot = `/ssd2/go`\n")
      wf.write("const TheVersion = `NMhack +feedface`\n")
      wf.write("const Goexperiment = ``\n")
      wf.write("const StackGuardMultiplier = 1\n")
  except IOError:
    u.error("unable to open %s for writing" % zgo)


def bootstrap(repo, goroot, variant):
  """Build a go repo with a specific go root."""
  f = "build.%s.sh" % repo
  if os.path.exists(f):
    rmfile(f)
  try:
    with open(f, "w") as wf:
      wf.write("#!/bin/sh\n")
      wf.write("set -x\n")
      wf.write("export PATH=%s/bin:$PATH\n" % goroot)
      wf.write("export GOROOT_BOOTSTRAP=%s\n" % goroot)
      vtag = variants[variant]["tag"]
      if vtag == "gccgo" or vtag == "gollvm":
        wf.write("export LD_LIBRARY_PATH=%s/lib64\n" % goroot)
      wf.write("cd %s/src\n" % repo)
      wf.write("export GOOS=linux\n")
      wf.write("export GOARCH=amd64\n")
      wf.write("bash make.bash -v\n")
      wf.write("if [ $? != 0 ]; then\n")
      wf.write("  echo '*** FAIL ***'\n")
      wf.write("  exit 1\n")
      wf.write("fi\n")
      wf.write("# Hack: copy bootstrap compiler into correct place\n")
      wf.write("cd ../pkg\n")
      wf.write("rm -f tool/linux_amd64/compile\n")
      wf.write("mv bootstrap/bin/compile tool/linux_amd64/compile\n")
      wf.write("if [ $? != 0 ]; then\n")
      wf.write("  echo '*** FAIL copy ***'\n")
      wf.write("  exit 1\n")
      wf.write("fi\n")
  except IOError:
    u.error("unable to open %s for writing" % f)
  outfile = "err.%s.txt" % repo
  docmderrout("sh %s" % f, outfile)
  docmd("touch %s/token.txt" % repo)


def benchprep(repo, variant):
  """Prepare for running a benchmark build."""
  # Here the general idea is to run 'go build' with -a -x -work
  # and capture the compilation commands. We then emit a script
  # that will replay just the compilation commands.
  f = "prep.%s.sh" % repo
  here = os.getcwd()
  goroot = os.path.join(here, repo)
  if os.path.exists(f):
    rmfile(f)
  try:
    with open(f, "w") as wf:
      wf.write("#!/bin/sh\n")
      wf.write("set -x\n")
      wf.write("export PATH=%s/bin:$PATH\n" % goroot)
      vtag = variants[variant]["tag"]
      if vtag == "gccgo" or vtag == "gollvm":
        wf.write("export LD_LIBRARY_PATH=%s/lib64\n" % goroot)
      wf.write("cd %s/src/cmd/compile\n" % repo)
      wf.write("rm -rf %s/pkg/*inux_amd64/cmd/compile\n" % goroot)
      wf.write("go clean -cache\n")
      wf.write("go build -work -p 1 -x -o compile.new .\n")
      wf.write("if [ $? != 0 ]; then\n")
      wf.write("  echo '*** FAIL ***'\n")
      wf.write("  exit 1\n")
      wf.write("fi\n")
      wf.write("exit 0\n")
  except IOError:
    u.error("unable to open %s for writing" % f)
  outfile = "err.preprun.%s.txt" % repo
  docmderrout("sh %s" % f, outfile)
  scriptfile = "%s/runbench.%s.sh" % (here, repo)
  if not flag_dryrun:
    # harvest output
    doscmd("capture-go-compiler-invocation.py "
           "-N -A -C -i %s -o %s" % (outfile, scriptfile))
    # capture work dir
    workdir = None
    try:
      regex = re.compile(r"WORK=(\S+)$")
      with open(outfile, "r") as rf:
        lines = rf.readlines()
        for line in lines:
          m = regex.match(line)
          if m:
            workdir = m.group(1)
            break
    except IOError:
      u.error("open failed for %s" % outfile)
    if not workdir:
      u.error("could not find WORKDIR setting in %s" % outfile)
  else:
    workdir = "dummywork"
  tup = (workdir, scriptfile)
  return tup


def benchmark(repo, runscript, wrapcmd, tag):
  """Run benchmark build."""
  f = "bench.%s.%s.sh" % (repo, tag)
  u.verbose(1, "... running %s" % f)
  if os.path.exists(f):
    rmfile(f)
  try:
    with open(f, "w") as wf:
      wf.write("#!/bin/sh\n")
      wf.write("set -x\n")
      if flag_gomaxprocs:
        wf.write("export GOMAXPROCS=%s\n" % flag_gomaxprocs)
      wf.write("export LD_LIBRARY_PATH=%s/lib64\n" % gccgo_install)
      wf.write("go clean -cache\n")
      wf.write("cd %s/src/cmd/compile\n" % repo)
      wf.write("%s sh %s\n" % (wrapcmd, runscript))
      wf.write("if [ $? != 0 ]; then\n")
      wf.write("  echo '*** FAIL ***'\n")
      wf.write("  exit 1\n")
      wf.write("fi\n")
      wf.write("exit 0\n")
  except IOError:
    u.error("unable to open %s for writing" % f)
  outfile = "err.benchrun.%s.%s.txt" % (repo, tag)
  docmderrout("sh %s" % f, outfile)


def ppo_append(ppo, cmd, outf):
  """Append cmd to ppo command file."""
  global ppolines
  cmd = cmd.replace(r"$", r"\$")
  if flag_dryrun:
    u.verbose(0, "%s" % cmd)
    return
  errf = "/tmp/ppo-err.%d.%d" % (ppolines, len(cmd))
  if not outf:
    outf = "/tmp/ppo-out.%d.%d" % (ppolines, len(cmd))
  ppolines += 1
  ppo.write("%s 1> %s 2> %s &\n" % (cmd, outf, errf))
  ppo.write("PIDS=\"$PIDS $!:%s\"\n" % errf)


def annotate(func, tag, fn, ppo, perf_work):
  """Run 'perf annotate' on a specified function."""
  # Check to see if function present in perf report
  repfile = "rep.%s.txt" % tag
  if not flag_dryrun:
    try:
      # 0.16%  compile  compile           [.] runtime.mapdelete
      regex_fn = re.compile(r"^\s*(\S+)%\s+\S+.+\]\s+(\S+)$")
      found = False
      with open(repfile, "r") as rf:
        lines = rf.readlines()
        for line in lines:
          fm = regex_fn.match(line)
          if fm and fm.group(2) == func:
            found = True
    except IOError:
      u.warning("open failed for %s" % repfile)
      return
    if not found:
      u.warning("skipping annotate for %s, could not "
                "find in %s" % (func, repfile))
      return
  report_file = "%s/ann%d.%s.txt" % (perf_work, fn, tag)
  ppo_append(ppo,
             "%s annotate -i perf.data.%s "
             "-s %s" % (flag_perf, tag, func), report_file)
  generated_reports[report_file] = 1


def disas(func, repo, tag, fn, ppo, perf_work):
  """Disassemble a specified function."""
  # 00691d40 g     F .text      00000632 ssa.applyRewrite
  regex = re.compile(r"^(\S+)\s.+\s(\S+)\s+(\S+)$")
  tgt = "%s/pkg/tool/linux_amd64/compile" % repo
  u.verbose(1, "looking for %s in output of objdump -t %s" % (func, tgt))
  if flag_dryrun:
    return
  lines = u.docmdlines("objdump -t %s" % tgt)
  hexstaddr = None
  hexsize = None
  for line in lines:
    m = regex.match(line)
    if m:
      name = m.group(3)
      if name == func:
        # Found
        hexstaddr = m.group(1)
        hexsize = m.group(2)
        break
  if not hexstaddr:
    u.verbose(0, "... could not find %s in "
              "output of objdump, skipping" % func)
    return
  try:
    staddr = int(hexstaddr, 16)
    size = int(hexsize, 16)
    enaddr = staddr + size
  except ValueError:
    u.verbose(0, "... malformed staddr/size (%s, %s) "
              "for %s, skipping" % (hexstaddr, hexsize, func))
    return
  asm_file = "%s/asm%d.%s.txt" % (perf_work, fn, tag)
  ppo_append(ppo,
             "objdump -dl --start-address=0x%x "
             "--stop-address=0x%x %s" % (staddr, enaddr, tgt),
             asm_file)
  generated_reports[asm_file] = 1
  pprof_file = "%s/pprofdis%d.%s.txt" % (perf_work, fn, tag)
  ppo_append(ppo,
             "pprof --disasm=%s perf.data.%s " % (func, tag),
             pprof_file)
  generated_reports[pprof_file] = 1


def emit_pprof_postprocess(pprof_work, variant, ppo):
  """Emit commands to generate pprof reports."""
  outdir = pprof_work
  cmd = "do-pprof-cpuprofile.py"
  binary = "bootstrap.%s/pkg/tool/linux_amd64/compile" % variant
  tag = variant
  if flag_dryrun:
    infstr = "somefiles.p:otherfiles.p"
  else:
    infiles = []
    reg = re.compile(r"^p\d+\.p$")
    for item in os.listdir(outdir):
      m = reg.match(item)
      if m:
        infiles.append("%s/%s" % (outdir, item))
    infstr = ":".join(infiles)
  ppo_append(ppo, "%s -i %s -o %s "
             "-b %s -t %s" % (cmd, infstr, outdir, binary, tag), None)


def process_variant(variant, ppo):
  """Benchmark a specific variant."""
  here = os.getcwd()
  build_dir = "bootstrap.%s" % variant
  installation = variants[variant]["install"]
  if flag_skip_bootstrap and os.path.exists("%s/token.txt" % build_dir):
    u.verbose(0, "... skipping bootstrap for %s" % variant)
  else:
    bootstrap(build_dir, installation, variant)
  work = None
  if flag_skip_benchrun:
    return

  # Step 1: run for time.
  work, runit = benchprep(build_dir, variant)
  benchmark(build_dir, runit, "/usr/bin/time", "tim")

  # Step 2: perf run
  if flag_doperf:
    here = os.getcwd()
    perf_work = "%s/perf.files.%s" % (here, variant)
    dormdir(perf_work)
    docmd("mkdir -p %s" % perf_work)
    pdfile = "%s/perf.data.%s" % (perf_work, variant)
    perfwrap = "%s record -o %s" % (flag_perf, pdfile)
    benchmark(build_dir, runit, perfwrap, "perf")
    # report
    report_file = "%s/rep.%s.txt" % (perf_work, variant)
    docmderrout("%s report -i %s" % (flag_perf, pdfile), report_file)
    u.trim_perf_report_file(report_file)
    generated_reports[report_file] = 1

    # annotate and disassemble a couple of functions
    fn = 1
    for tup in interesting_funcs:
      f, gf = tup
      vtag = variants[variant]["tag"]
      if vtag == "gccgo" or vtag == "gollvm":
        f = gf
      annotate(f, variant, fn, ppo, perf_work)
      disas(f, build_dir, variant, fn, ppo, perf_work)
      fn += 1

  # Step 3: pprof run
  if flag_dopprof:
    here = os.getcwd()
    pprof_work = "%s/pprof.files.%s" % (here, variant)
    dormdir(pprof_work)
    docmd("mkdir -p %s" % pprof_work)
    benchmark(build_dir, runit, "CPUPROFILE=%s" % pprof_work, "pprof")
    emit_pprof_postprocess(pprof_work, variant, ppo)

  # Step 4: auto-FDO perf.data collection run
  if flag_collect_autofdo_perf:
    here = os.getcwd()
    autofdo_work = "%s/autofdoperf.files.%s" % (here, variant)
    dormdir(autofdo_work)
    docmd("mkdir -p %s" % autofdo_work)
    benchmark(build_dir, runit, "AUTOFDOPROFILE=%s" % autofdo_work,
              "autofdocollect")

  if work:
    if flag_keepwork:
      u.verbose(1, "keeping work dir %s" % work)
    else:
      u.verbose(1, "removing work dir %s" % work)
      rmdir(work)


def open_pprof_output():
  """Open pprof script output file."""
  if flag_dryrun:
    return (None, None)
  try:
    outf = tempfile.NamedTemporaryFile(mode="w", delete=True)
    ppo = open(outf.name, "w")
  except IOError:
    u.verbose(0, "open failed for %s" % outf.name)
  ppo.write("#!/bin/sh\n")
  ppo.write("PIDS=\n")
  return (outf, ppo)


def run_ppo_cmds(outf, ppo):
  """Run script containing pprof cmds."""
  if flag_dryrun:
    return
  ppo.write("for PF in $PIDS\n")
  ppo.write("do\n")
  ppo.write("  P=`echo $PF | cut -f1 -d:`\n")
  ppo.write("  F=`echo $PF | cut -f2 -d:`\n")
  ppo.write("  wait $P\n")
  ppo.write("  if [ $? != 0 ]; then\n")
  ppo.write("    echo +++ subcommand failed:\n")
  ppo.write("    cat $F\n")
  ppo.write("    rm -f $F\n")
  ppo.write("    exit 1\n")
  ppo.write("  fi\n")
  ppo.write("  rm -f $F\n")
  ppo.write("done\n")
  ppo.flush()
  doscmd("sh %s" % outf.name)
  ppo.close()


def generate_html():
  """Post-process reports to create html out dir."""
  docmd("rm -rf html")
  docmd("mkdir html")
  reports = " ".join(generated_reports)
  docmd("cp %s html" % reports)
  hreports = " ".join(["html/%s" % y for y in generated_reports])
  docmd("render-asm.py %s" % hreports)
  docmd("rm %s" % hreports)


def order_variants():
  """Select variants by order."""
  ret = [None] * len(variants)
  for v in variants:
    ret[variants[v]["order"]] = v
  return ret


def perform():
  """Main routine for script."""
  repo_setup()
  outf, ppo = open_pprof_output()
  ordered = order_variants()
  for v in ordered:
    if variants[v]["install"]:
      process_variant(v, ppo)
  run_ppo_cmds(outf, ppo)
  if flag_genhtml:
    generate_html()


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options]

    options:
    -e    echo commands before executing
    -d    increase debug msg verbosity level
    -B    skip bootstrap if dirs already present
    -N    skip benchmark run (useful mainly for script debugging)
    -D    dryrun mode (echo commands but do not execute)
    -H    emit HTML for assembly dumps and reports
    -g X  benchmark the go compiler drawn from go root X
    -G X  benchmark the gccgo compiler drawn from gccgo root X
    -L X  benchmark the gollvm compiler drawn from gollvm root X
    -M N  set GOMAXPROCS to N prior to bench run
    -P    preserve 'go build' workdirs
    -F V  process variant 'V' first (debugging)
    -O V  process only variant 'V'
    -A P  path to AutoFDO profile is P (for gollvm variant)
    -T X  apply alternate tag X to run results
    -Z    include linux 'perf' runs
    -Q    collect perf.data files for AutoFDO purposes
    -W P  path to 'perf' is P

    Example usage:

    $ mkdir /tmp/benchrun
    $ cd /tmp/benchrun
    $ %s \\
        -g /ssd/mygorepo \\
        -G /ssd/mygccgoinstall \\
        -L /ssd/mygollvminstall

    The command above will:
    - run git clone to download a copy of the Go repo
    - copy said repo into two workspaces: bootstrap.gccgo and bootstrap.gc
    - run make.bash in each workspace, with GOROOT_BOOTSTRAP
      set to gccgo for the gccgo copy
    - pick out the gccgo-compiled 'compile' and place into regular location
      (e.g. "cd pkg; mv bootstrap/bin/compile tool/linux_amd64/compile"
    - run a preparatory "go build" of the compiler in each workspace, capturing
      the compiler invocations
    - rerun the captured compiler with perf.data collection + timings,
      to compare the performance of "gc-compiled" vs "gccgo-compiled"
      cs "gollvm-compiled" compiler binary

    """ % (me, me)

  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_echo, flag_dryrun, flag_skip_bootstrap, flag_skip_benchrun
  global flag_keepwork, go_install, gccgo_install, flag_genhtml
  global flag_gomaxprocs, gollvm_install, flag_perf, flag_doperf
  global flag_autofdoprofile, flag_othertag, flag_collect_autofdo_perf

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "deBZNMQ:DHPg:G:L:F:W:A:T:O:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  if args:
    usage("unknown extra args: %s" % " ".join(args))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-D":
      u.verbose(0, "+++ dry run mode")
      flag_dryrun = True
      flag_echo = True
    elif opt == "-e":
      flag_echo = True
    elif opt == "-B":
      flag_skip_bootstrap = True
    elif opt == "-N":
      flag_skip_benchrun = True
    elif opt == "-P":
      flag_keepwork = True
    elif opt == "-Z":
      flag_doperf = True
    elif opt == "-A":
      if not os.path.exists(arg):
        usage("can't access -A argument %s" % arg)
      u.verbose(1, "using AutoFDO profile file %s" % arg)
      flag_autofdoprofile = arg
    elif opt == "-H":
      flag_genhtml = True
    elif opt == "-M":
      u.verbose(1, "setting GOMAXPROCS to %s on bench run" % arg)
      flag_gomaxprocs = arg
    elif opt == "-Q":
      u.verbose(1, "enabling AUTOFDOPROFILE collect for this run")
      flag_collect_autofdo_perf = True
    elif opt == "-W":
      u.verbose(1, "selecting %s as perf path" % arg)
      flag_perf = arg
    elif opt == "-T":
      flag_othertag = arg
      u.verbose(0, "applying alternate tag %s to run output" % arg)
    elif opt == "-F":
      if arg not in variants:
        usage("can't find specified variant '%s'" % arg)
      u.verbose(1, "selecting %s as first variant" % arg)
      oord = variants[arg]["order"]
      if oord != 0:
        firstvariant = ""
        for v in variants:
          vord = variants[v]["order"]
          if vord == 0:
            firstvariant = v
            break
        variants[arg]["order"] = 0
        variants[firstvariant]["order"] = oord
    elif opt == "-O":
      if arg not in variants:
        usage("can't find specified variant '%s'" % arg)
      u.verbose(1, "selecting %s as only variant" % arg)
      todel = []
      for v in variants:
        if v != arg:
          todel.append(v)
      for v in todel:
        del variants[v]
      variants[arg]["order"] = 0
    elif opt == "-G":
      u.verbose(1, "setting gccgo_install to %s" % arg)
      gccgo_install = arg
      variants["gccgo"]["install"] = gccgo_install
    elif opt == "-L":
      u.verbose(1, "setting gollvm_install to %s" % arg)
      gollvm_install = arg
      variants["gollvm"]["install"] = gollvm_install
    elif opt == "-g":
      u.verbose(1, "setting go_install to %s" % arg)
      go_install = arg
      variants["gc"]["install"] = go_install

  flavors = {}
  for v in variants:
    t = variants[v]["tag"]
    flavors[t] = 1

  # Make sure go install look ok
  if "gc" in flavors:
    if not go_install:
      usage("specify Go installation with -g option")
    if not os.path.exists(go_install):
      usage("unable to locate go installation %s" % go_install)
    if not os.path.isdir(go_install):
      usage("go installation %s not a directory" % go_install)
    gobin = os.path.join(go_install, "bin/go")
    if not os.path.exists(gobin):
      usage("bad go installation, can't access %s" % gobin)

  # Make sure gccgo install looks ok if specified
  if "gccgo" in flavors:
    if not gccgo_install:
      usage("specify Gccgo installation with -G option")
    if not os.path.exists(gccgo_install):
      usage("unable to locate gccgo installation %s" % gccgo_install)
    if not os.path.isdir(gccgo_install):
      usage("gccgo installation %s not a directory" % gccgo_install)
    gccgobin = os.path.join(gccgo_install, "bin/gccgo")
    if not os.path.exists(gccgobin):
      usage("bad gccgo installation, can't access %s" % gccgobin)

  # Make sure gollvm install looks ok if specified
  if "gollvm" in flavors:
    if not gollvm_install:
      usage("specify Gollvm installation with -L option")
    if not os.path.exists(gollvm_install):
      usage("unable to locate gollvm installation %s" % gollvm_install)
    if not os.path.isdir(gollvm_install):
      usage("gollvm installation %s not a directory" % gollvm_install)
    gollvmbin = os.path.join(gollvm_install, "bin/llvm-goc")
    if not os.path.exists(gollvmbin):
      usage("bad gollvm installation, can't access %s" % gollvmbin)

  # Fill in derived variants
  for v in variants:
    if "derived" in variants[v]:
      der = variants[v]["derived"]
      variants[v]["install"] = variants[der]["install"]
      u.verbose(1, "using %s install for variant %s" % (v, der))


#
#......................................................................
#
# Main portion of script
#
parse_args()
u.setdeflanglocale()
perform()
exit(0)
