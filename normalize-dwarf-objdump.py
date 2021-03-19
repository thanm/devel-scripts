#!/usr/bin/python3
"""Filter to normalize/canonicalize objdump --dwarf=info dumps.

Reads stdin, normalizes / canonicalizes and/or strips the output of objdump
--dwarf to make it easier to "diff".

Support is provided for rewriting absolute offsets within the dump to relative
offsets. A chunk like

 <2><2d736>: Abbrev Number: 5 (DW_TAG_variable)
    <2d737>   DW_AT_name        : oy
    <2d73a>   DW_AT_decl_line   : 23
    <2d73b>   DW_AT_location    : 0x15eee8      (location list)
    <2d73f>   DW_AT_type        : <0x2f1f2>

Would be rewritten as

 <2><0>: Abbrev Number: 5 (DW_TAG_variable)
    <0>   DW_AT_name        : oy
    <0>   DW_AT_decl_line   : 23
    <0>   DW_AT_location    : ...      (location list)
    <0>   DW_AT_type        : <0x10>

You can also request that all offsets and PC info be stripped, although that can
can obscure some important differences. Abstract origin references are tracked
and annotated (unless disabled).

"""

import getopt
import os
import re
import sys

import script_utils as u

# Input and output file (if not specified, defaults to stdin/stdout)
flag_infile = None
flag_outfile = None

# Perform normalization
flag_normalize = True

# Compile units to be included in dump.
flag_compunits = {}

# Strip offsets if true
flag_strip_offsets = False

# Strip hi/lo PC and location lists
flag_strip_pcinfo = False

# Annotate abstract origin refs
flag_annotate_abstract = True

# Strip these
pcinfo_attrs = {"DW_AT_low_pc": 1, "DW_AT_high_pc": 1}

# Untracked DW refs
untracked_dwrefs = {}

# Line buffer
linebuf = None
linebuffered = False

#......................................................................

# Regular expressions to match:

# Begin-DIE preamble
bdiere = re.compile(r"^(\s*)\<(\d+)\>\<(\S+)\>\:(.*)$")
bdiezre = re.compile(r"^\s*Abbrev Number\:\s+0\s*$")
bdiebodre = re.compile(r"^\s*Abbrev Number\:\s+\d+\s+\(DW_TAG_(\S+)\)\s*$")

# Within-DIE regex
indiere = re.compile(r"^(\s*)\<(\S+)\>(\s+)(DW_AT_\S+)(\s*)\:(.*)$")
indie2re = re.compile(r"^(\s*)\<(\S+)\>(\s+)(Unknown\s+AT\s+value)(\s*)\:(.*)$")

# For grabbing dwarf ref from attr value
absore = re.compile(r"^\s*\<\S+\>\s+DW_AT_\S+\s*\:\s*\<0x(\S+)\>.*$")

# Attr value dwarf offset
attrdwoffre = re.compile(r"^(.*)\<0x(\S+)\>(.*)$")


def compute_reloff(absoff, origin):
  """Compute relative offset from absolute offset."""
  oabs = int(absoff, 16)
  if not flag_normalize:
    return oabs
  odec = int(origin, 16)
  delta = oabs - odec
  return delta


def abstorel(val, diestart):
  """Convert absolute to relative DIE offset."""

  # FIXME: this will not handle backwards refs; that would
  # require multiple passes.
  m1 = attrdwoffre.match(val)
  if m1:
    absref = m1.group(2)
    if absref in diestart:
      val = re.sub(r"<0x%s>" % absref, r"<0x%x>" % diestart[absref], val)
      u.verbose(3, "abs %s converted to rel %s" % (absref, val))
      return (0, val)
    return (1, absref)
  return (2, None)


def munge_attrval(attr, oval, diestart):
  """Munge attr value."""

  # Convert abs reference to rel reference.
  # FIXME: this will not handle backwards refs; that would
  # require multiple passes.
  code, val = abstorel(oval, diestart)
  if code == 1:
    absref = val
    if absref in untracked_dwrefs:
      val = untracked_dwrefs[absref]
    else:
      n = len(untracked_dwrefs)
      if flag_normalize:
        unk = (" <untracked %d>" % (n+1))
      else:
        unk = (" <untracked 0x%s>" % absref)
      untracked_dwrefs[absref] = unk
      val = unk
  if code == 2:
    val = oval
  if flag_strip_pcinfo:
    if attr in pcinfo_attrs:
      val = "<stripped>"
  return val


def read_line(inf):
  """Read an input line."""
  global linebuffered
  global linebuf
  if linebuffered:
    linebuffered = False
    u.verbose(3, "buffered line is %s" % linebuf)
    return linebuf
  line = inf.readline()
  u.verbose(3, "line is %s" % line.rstrip())
  return line


def unread_line(line):
  """Unread an input line."""
  global linebuffered
  global linebuf
  u.verbose(3, "unread_line on %s" % line.rstrip())
  if linebuffered:
    u.error("internal error: multiple line unread")
  linebuffered = True
  linebuf = line


def read_die(inf, outf):
  """Reads in and returns the next DIE."""
  lines = []
  indie = False
  while True:
    line = read_line(inf)
    if not line:
      break
    m1 = bdiere.match(line)
    if not indie:
      if m1:
        lines.append(line)
        indie = True
        continue
      outf.write(line)
    else:
      if m1:
        unread_line(line)
        break
      m2 = indiere.match(line)
      if not m2:
        m2 = indie2re.match(line)
      if not m2:
        unread_line(line)
        break
      lines.append(line)
  u.verbose(2, "=-= DIE read:")
  for line in lines:
    u.verbose(2, "=-= %s" % line.rstrip())
  return lines


def emit_die(lines, outf, origin, diename, diestart):
  """Emit body of DIE."""
  # First line
  m1 = bdiere.match(lines[0])
  if not m1:
    u.error("internal error: first line of DIE "
            "should match bdiere: %s" % lines[0])
  sp = m1.group(1)
  depth = m1.group(2)
  absoff = m1.group(3)
  rem = m1.group(4)
  off = compute_reloff(absoff, origin)
  if flag_strip_offsets:
    outf.write("%s<%s>:%s\n" % (sp, depth, rem))
  else:
    outf.write("%s<%s><%0x>:%s\n" % (sp, depth, off, rem))
  # Remaining lines
  for line in lines[1:]:
    m2 = indiere.match(line)
    if not m2:
      m2 = indie2re.match(line)
    if not m2:
      u.error("internal error: m2 match failed on attr line")
    sp1 = m2.group(1)
    absoff = m2.group(2)
    sp2 = m2.group(3)
    attr = m2.group(4)
    sp3 = m2.group(5)
    rem = m2.group(6)
    addend = ""
    off = compute_reloff(absoff, origin)
    u.verbose(3, "attr is %s" % attr)
    # Special sauce if abs origin.
    if attr == "DW_AT_abstract_origin":
      m3 = absore.match(line)
      if m3:
        absoff = m3.group(1)
        reloff = compute_reloff(absoff, origin)
        if reloff in diename:
          addend = "// " + diename[reloff]
      else:
        u.verbose(2, "absore() failed on %s\n", line)
    # Post-process attr value
    rem = munge_attrval(attr, rem, diestart)
    # Emit
    if flag_strip_offsets:
      outf.write("%s%s%s:%s%s%s\n" % (sp1, sp2, attr,
                                      sp3, rem, addend))
    else:
      outf.write("%s<%0x>%s%s:%s%s%s\n" % (sp1, off, sp2,
                                           attr, sp3, rem, addend))


def attrval(lines, tattr):
  """Return the specified attr for this DIE (or empty string if no name)."""
  for line in lines[1:]:
    m2 = indiere.match(line)
    if not m2:
      m2 = indie2re.match(line)
    if not m2:
      u.error("attr match failed for %s" % line)
    attr = m2.group(4)
    if attr == tattr:
      rem = m2.group(6)
      return rem.strip()
  return ""


def perform_filt(inf, outf):
  """Read inf and filter contents to outf."""

  # Records DIE starts: hex string => new offset
  diestart = {}

  # Maps rel DIE offset to name. Note that not all DIEs have names.
  diename = {}

  # Origin (starting absolute offset)
  origin = None

  # Set to true if output is filtered off
  filtered = False

  if flag_compunits:
    u.verbose(1, "Selected compunits:")
    for cu in sorted(flag_compunits):
      u.verbose(1, "%s" % cu)

  # Read input
  while True:
    dielines = read_die(inf, outf)
    if not dielines:
      break

    # Process starting line of DIE
    line1 = dielines[0]
    m1 = bdiere.match(line1)
    if not m1:
      u.error("internal error: first line of DIE should match bdiere")
    absoff = m1.group(3)
    rem = m1.group(4)
    if not origin:
      u.verbose(2, "origin set to %s" % absoff)
      origin = absoff
    off = compute_reloff(absoff, origin)
    diestart[absoff] = off

    # Handle zero terminators.
    if bdiezre.match(rem):
      if not filtered:
        emit_die(dielines, outf, origin, diename, diestart)
      continue

    # See what flavor of DIE this is to adjust filtering.
    m2 = bdiebodre.match(rem)
    if not m2:
      u.error("bdiebodre/bdiezre match failed on: '%s'" % rem)
    tag = m2.group(1)
    u.verbose(2, "=-= tag = %s" % tag)
    if flag_compunits and tag == "compile_unit":
      name = attrval(dielines, "DW_AT_name")
      if name:
        if name in flag_compunits:
          u.verbose(1, "=-= output enabled since %s is in compunits" % name)
          filtered = False
        else:
          u.verbose(1, "=-= output disabled since %s not in compunits" % name)
          filtered = True

    # Emit die if not filtered
    if not filtered:
      u.verbose(2, "=-= emit DIE")
      emit_die(dielines, outf, origin, diename, diestart)
    else:
      u.verbose(2, "=-= flush DIE (filtered): %s" % dielines[0])


def perform():
  """Main driver routine."""
  inf = sys.stdin
  outf = sys.stdout
  if flag_infile:
    try:
      inf = open(flag_infile, "rb")
    except IOError as e:
      u.error("unable to open input file %s: "
              "%s" % (flag_infile, e.strerror))
  if flag_outfile:
    try:
      outf = open(flag_outfile, "wb")
    except IOError as e:
      u.error("unable to open output file %s: "
              "%s" % (flag_outfile, e.strerror))
  perform_filt(inf, outf)
  if flag_infile:
    inf.close()
  if flag_outfile:
    outf.close()


def usage(msgarg):
  """Print usage and exit."""
  me = os.path.basename(sys.argv[0])
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print("""\
    usage:  %s [options] < input > output

    options:
    -d    increase debug msg verbosity level
    -i F  read from input file F
    -o G  write to output file O
    -u X  emit only compile unit match name X
    -S    strip DWARF offsets from die/attr dumps
    -P    strip location lists, hi/lo PC attrs
    -A    do not annotate abstract origin refs with name
    -N    don't rewrite offsets (turn normalization off)

    """ % me)
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_infile, flag_outfile, flag_strip_offsets, flag_strip_pcinfo
  global flag_annotate_abstract, flag_normalize

  try:
    optlist, _ = getopt.getopt(sys.argv[1:], "di:o:u:SPAN")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-i":
      flag_infile = arg
    elif opt == "-o":
      flag_outfile = arg
    elif opt == "-S":
      flag_strip_offsets = True
    elif opt == "-P":
      flag_strip_pcinfo = True
    elif opt == "-A":
      flag_annotate_abstract = False
    elif opt == "-N":
      flag_normalize = False
    elif opt == "-u":
      flag_compunits[arg] = 1


parse_args()
u.setdeflanglocale()
perform()
