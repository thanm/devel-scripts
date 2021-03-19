#!/usr/bin/python3
"""Generate a DOT graph showing load module dependencies.

Runs objdump to gather load module dependency relationships.

"""

from collections import defaultdict
import getopt
import locale
import os
import re
import shlex
import subprocess
import sys
import script_utils as u


# Output DOT file
flag_outfile = None

# List of input files collected from command line
flag_input_files = []
input_sonames = {}

# Selection for -r arg (either 32 or 64)
flag_restrict_elf = None

# Objdump cmd, determined on the fly
objdump_cmd = None

# Target or host mode
flag_filemode = "target"

# Complain if input files are not in .../symbols directory
flag_check_in_symbols = True

# Prune out common *.so files
flag_prune = False

# Include backward slice of depth N
flag_backward_slice = 0

# Setting of $ANDROID_BUILD_TOP
abt = ""

# Setting of $ANDROID_PRODUCT_OUT
apo = ""

# Setting of $ANDROID_HOST_OUT
aho = ""

# Load module dependency table. Key is load module name (not path),
# value is dict of dependency names. rdepends is reverse graph
depends = defaultdict(lambda: defaultdict(str))
rdepends = defaultdict(lambda: defaultdict(str))

# Populated with all possible load modules of interest. Key
# is load module path, value is 0 (unvisited) or 1 (visited).
all_loadmodules = {}

# Maps load module base name to dict of paths
base_to_paths = defaultdict(lambda: defaultdict(str))

# Things to omit for -p option
toprune = {"libm.so": 1, "libc.so": 1, "libdl.so": 1, "libc++.so": 1}

# Node colors (key is soname)
nodecolor = {}


def in_symbols_dir(filename):
  """Make sure input file is part of $ANROID_PRODUCT_OUT/symbols."""

  if flag_filemode == "host" or not flag_check_in_symbols:
    return True

  u.verbose(2, "in_symbols_dir(%s)" % filename)
  smatch = re.compile(r"^(\S+)\/symbols\/\S+$")
  sm = smatch.match(filename)
  if sm is None:
    u.verbose(2, "/symbols/ match failed for %s" % filename)
    return False
  pre = sm.group(1)
  u.verbose(2, "pre=%s apo=%s abt=%s" % (pre, apo, abt))
  if pre == apo:
    return True
  fp = "%s/%s" % (abt, pre)
  return fp == apo


def determine_objdump(filename):
  """Figure out what flavor of object dumper we should use."""
  global objdump_cmd

  lines = u.docmdlines("file %s" % filename)
  matchers = [(re.compile(r".*ELF.+ARM aarch64"),
               "aarch64-linux-android-objdump"),
              (re.compile(r".*ELF.+ARM"),
               "arm-linux-androideabi-objdump"),
              (re.compile(r".*ELF.+x86\-64"),
               "objdump"),
              (re.compile(r".*ELF.+Intel"),
               "objdump")]
  for l in lines:
    for tup in matchers:
      m = tup[0]
      res = m.match(l)
      if res is None:
        continue
      objdump_cmd = tup[1]
      return
  u.error("unable to determine objdump flavor to use on %s" % filename)


def run_objdump_cmd(cargs, filename):
  """Run objdump with specified args, returning list of lines."""

  if not objdump_cmd:
    determine_objdump(filename)

  cmd = "%s %s %s" % (objdump_cmd, cargs, filename)
  u.verbose(2, "objdump cmd: %s" % cmd)
  splargs = shlex.split(cmd)
  mypipe = subprocess.Popen(splargs, stdout=subprocess.PIPE)
  pout, _ = mypipe.communicate()
  if mypipe.returncode != 0:
    u.error("command failed (rc=%d): cmd was %s" % (mypipe.returncode, cmd))
  encoding = locale.getdefaultlocale()[1]
  decoded = pout.decode(encoding)
  return decoded.strip().split("\n")


def skip_this_elf(filename, lines, eflav):
  """Return whether we should skip this elf."""
  matcher = re.compile(r"^\S+:\s+file format elf(\d\d)\-")
  for line in lines:
    if not line:
      continue
    m = matcher.match(line)
    if m:
      dd = int(m.group(1))
      if dd != 32 and dd != 64:
        u.error("internal error: bad elf %s flavor %d "
                "(line %s)" % (filename, dd, line))
      if dd != eflav:
        # Not correct flavor
        return True
      else:
        return False
  u.error("internal error: could not find file format line")


def examine_deps(filename):
  """Run objdump to collect depends info."""

  u.verbose(2, "examine_deps(%s)" % filename)
  objdump_args = "-p"
  lines = run_objdump_cmd(objdump_args, filename)
  if flag_restrict_elf and skip_this_elf(filename, lines, flag_restrict_elf):
    u.verbose(1, "skipping file %s, wrong elf flavor" % filename)
    return None

  bn = os.path.basename(filename)
  u.verbose(2, "examining objdump output for %s (%s)" % (bn, filename))

  # Pattern we're looking for in the objdump output
  matcher = re.compile(r"^\s+(\S+)\s+(\S+)\s*$")

  deps = {}
  soname = None

  # Run through all of the lines:
  for line in lines:
    if not line:
      continue
    # Match
    m = matcher.match(line)
    if m:
      which = m.group(1)
      if which == "NEEDED":
        lm = m.group(2)
        deps[lm] = 1
        u.verbose(3, "file %s has dep %s" % (filename, lm))
      elif which == "SONAME":
        soname = m.group(2)

  if soname:
    if soname != bn:
      u.verbose(1, "soname %s disagrees with "
                "basename for file %s" % (soname, filename))
  else:
    soname = bn
  if deps:
    ddict = depends[soname]
    for d in deps:
      u.verbose(2, "processing dep %s -> %s" % (soname, d))
      ddict[d] = 1
      rdict = rdepends[d]
      rdict[soname] = 1

  return soname


def examinefile(filename):
  """Perform symbol analysis on specified file."""
  u.verbose(2, "examinefile(%s)" % filename)
  if filename not in all_loadmodules:
    fullpath = os.path.join(os.getcwd(), filename)
    if fullpath in all_loadmodules:
      filename = fullpath
    else:
      u.warning("unable to visit %s (not "
                "in %s out)" % (filename, flag_filemode))
      return
  if all_loadmodules[filename] == 1:
    return
  if not in_symbols_dir(filename):
    u.warning("%s: does not appear to be in "
              "%s/symbols directory? skipping" % (filename, apo))
    return

  soname = examine_deps(filename)
  if not soname:
    all_loadmodules[filename] = 1
    return
  worklist = []
  ddict = depends[soname]
  for dep in ddict:
    pdict = base_to_paths[dep]
    for path in pdict:
      if path in all_loadmodules and all_loadmodules[path] == 0:
        all_loadmodules[path] = 1
        worklist.append(path)
  for item in worklist:
    examine_deps(item)


def collect_all_loadmodules():
  """Collect names of all interesting loadmodules."""
  locations = None
  if flag_filemode == "target":
    locations = "%s/symbols/system" % apo
  else:
    locations = "%s/bin %s/lib64" % (aho, aho)
  u.verbose(1, "collecting loadmodules from %s" % locations)
  cmd = "find %s -type f -print" % locations
  u.verbose(1, "find cmd: %s" % cmd)
  cargs = shlex.split(cmd)
  mypipe = subprocess.Popen(cargs, stdout=subprocess.PIPE)
  pout, _ = mypipe.communicate()
  if mypipe.returncode != 0:
    u.error("command failed (rc=%d): cmd was %s" % (mypipe.returncode, cmd))
  encoding = locale.getdefaultlocale()[1]
  decoded = pout.decode(encoding)
  lines = decoded.strip().split("\n")
  u.verbose(1, "found a total of %d load modules" % len(lines))
  for line in lines:
    path = line.strip()
    u.verbose(2, "adding LM %s" % path)
    all_loadmodules[path] = 0
    bn = os.path.basename(path)
    pdict = base_to_paths[bn]
    pdict[path] = 1
  if flag_backward_slice:
    for filearg in flag_input_files:
      bn = os.path.basename(filearg)
      if bn not in all_loadmodules:
        u.warning("argument %s not found in all_loadmodules "
                  "-- unable to compute slice" % filearg)


def get_nodename(soname, nodenames):
  """Generate DOT nodename."""
  if soname in nodenames:
    return nodenames[soname]
  nn = len(nodenames)
  seed = "".join([x if x.isalnum() else "_" for x in soname])
  nn = "%s_%d" % (seed, nn)
  nodenames[soname] = nn
  return nn


def emit_helper(fh, soname, mode, emitted, nodenames, restrictnodes):
  """Emit dot node."""
  if soname in emitted:
    return
  emitted[soname] = 1
  this_nn = get_nodename(soname, nodenames)
  if mode == "node":
    if not flag_prune or soname not in toprune:
      shape = "record"
      if soname in input_sonames:
        shape = "box3d"
      color = "lightblue"
      if soname in nodecolor:
        color = nodecolor[soname]
      fh.write(" %s [shape=%s,style=filled,"
               "fillcolor=%s,"
               "label=\"%s\"];\n" % (this_nn, shape, color, soname))
  ddict = depends[soname]
  for dep in ddict:
    res = False
    if restrictnodes and dep not in restrictnodes:
      res = True
    if flag_prune and dep in toprune:
      res = True
    if res:
      continue
    if mode == "edge":
      dep_nn = get_nodename(dep, nodenames)
      fh.write(" %s -> %s [style=\"solid,bold\","
               "color=black,weight=10,constraint=true];\n" % (this_nn, dep_nn))
    emit_helper(fh, dep, mode, emitted, nodenames, restrictnodes)


def collect_slice_nodes(seednode, depth):
  """Collect nodes in backward slice."""
  if depth == 0:
    return
  rval = {}
  rdict = rdepends[seednode]
  for rdep in rdict:
    rval[rdep] = 1
    nodecolor[rdep] = "lightyellow"
    collect_slice_nodes(rdep, depth-1)
  return rval


def emit_to_file(fh):
  """Emit output DOT to file or stdout."""
  fh.write("digraph \"graph\" {\n")
  fh.write(" overlap=false;\n")

  # Nodes
  nodes_emitted = {}
  nodenames = {}
  slicenodes = {}
  empty = {}
  restrictnodes = {}
  for filename in flag_input_files:
    bn = os.path.basename(filename)
    nodecolor[bn] = "red"
    input_sonames[bn] = 1
  u.verbose(1, "input sonames: %s" % " ".join(list(input_sonames.keys())))
  for filename in flag_input_files:
    bn = os.path.basename(filename)
    emit_helper(fh, bn, "node", nodes_emitted, nodenames, empty)
    preds = collect_slice_nodes(bn, flag_backward_slice)
    if preds:
      slicenodes.update(preds)
  restrictnodes.update(nodes_emitted)
  if slicenodes:
    u.verbose(1, "slice nodes: %s" % " ".join(list(slicenodes.keys())))
  for slicenode in slicenodes:
    restrictnodes[slicenode] = 1
    emit_helper(fh, slicenode, "node", nodes_emitted, nodenames, nodes_emitted)
  u.verbose(1, "restrictnodes: %s" % " ".join(list(restrictnodes.keys())))

  # Edges
  edges_emitted = {}
  for filename in flag_input_files:
    bn = os.path.basename(filename)
    emit_helper(fh, bn, "edge", edges_emitted, nodenames, empty)
  for slicenode in slicenodes:
    emit_helper(fh, slicenode, "edge", edges_emitted, nodenames, restrictnodes)
  fh.write("}\n")


def emit():
  """Emit output DOT."""
  if flag_outfile:
    u.verbose(1, "opening %s" % flag_outfile)
    fh = open(flag_outfile, "w")
  else:
    fh = sys.stdout
  emit_to_file(fh)


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options] <ELF files>

    options:
    -d         increase debug msg verbosity level
    -H         image of interest is host and not target (testing/debugging)
    -X         skip check to to make sure lib is in symbols dir
    -r {32,64} restrict analysis to just ELF-32 or just ELF-64 files
    -o F       write output DOT to file F (default is stdout)
    -p         omit nodes for common "base" libraries, including
               libc.so, libdl.so, libm.so, libc++.so
    -B N       include backward slice of depth N from input load modules

    Notes:
     - arguments are expected to be linked (.so or .exe) but unstripped

    """ % os.path.basename(sys.argv[0]))
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""

  global flag_check_in_symbols, flag_filemode
  global flag_input_files, apo, abt, aho
  global flag_restrict_elf, flag_outfile, flag_prune
  global flag_backward_slice

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "dpHB:Xr:o:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-p":
      flag_prune = True
    elif opt == "-H":
      flag_filemode = "host"
    elif opt == "-B":
      backdepth = int(arg)
      if backdepth < 1:
        u.usage("use positive arg for -B")
      flag_backward_slice = backdepth
    elif opt == "-r":
      if arg == "32":
        flag_restrict_elf = 32
      elif arg == "64":
        flag_restrict_elf = 64
      else:
        usage("argument to -r option must be either 32 or 64")
    elif opt == "-X":
      flag_check_in_symbols = False
    elif opt == "-o":
      flag_outfile = arg

  if not args:
    usage("specify at least one input file")

  for a in args:
    if not os.path.exists(a):
      usage("unable to read/access input arg %s" % a)
  flag_input_files = args

  abt = os.getenv("ANDROID_BUILD_TOP")
  if abt is None:
    u.error("ANDROID_BUILD_TOP not set (did you run lunch?)")
  apo = os.getenv("ANDROID_PRODUCT_OUT")
  if apo is None:
    u.error("ANDROID_PRODUCT_OUT not set (did you run lunch?)")
  aho = os.getenv("ANDROID_HOST_OUT")
  if aho is None:
    u.error("ANDROID_HOST_OUT not set (did you run lunch?)")

#----------------------------------------------------------------------
# Main portion of script
#

parse_args()
u.setdeflanglocale()
collect_all_loadmodules()
if flag_backward_slice:
  for f in all_loadmodules:
    examinefile(f)
else:
  for filearg in flag_input_files:
    examinefile(filearg)
emit()
