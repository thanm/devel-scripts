#!/usr/bin/python
"""Generate C++ code (used to create verge large C++ shared libs).

"""

import getopt
import os
import hashlib
import sys

import script_utils as u


flag_num_classes = 500
flag_class_prefix = None
flag_file_prefix = None


def perform():
  """Emit files."""
  cp = ""
  if flag_class_prefix:
    cp = "%s_" % flag_class_prefix
  fp = ""
  if flag_file_prefix:
    fp = "%s_" % flag_file_prefix
  f = open("%sgenerated.h" % fp, "w")
  for ii in range(flag_num_classes):
    f.write("class %sKlass%d {\n" % (cp, ii))
    f.write("  private:\n")
    f.write("    int x_, y_;\n")
    f.write("  public:\n")
    f.write("    %sKlass%d(int x);\n" % (cp, ii))
    f.write("    virtual ~%sKlass%d() { }\n" % (cp, ii))
    f.write("    virtual int flarbit(int y);\n")
    f.write("};\n\n")
  f.close()

  f = open("%sgenerated.cc" % fp, "w")
  f.write("#include \"%sgenerated.h\"\n" % fp)
  for ii in range(flag_num_classes):
    m = hashlib.md5()
    m.update("%s%sKlass%d" % (fp, cp, ii))
    hd = m.hexdigest() * 10
    f.write("%sKlass%d::%sKlass%d(int x) " % (cp, ii, cp, ii))
    f.write(" : x_(x + 0x%s), y_(x ^ 0x%s)\n" % (hd[0:8], hd[16:24]))
    f.write("{ }\n")
    f.write("int %sKlass%d::flarbit(int y) {\n" % (cp, ii))
    f.write("  static const int vec%s[1024*16] = {4,5,6};\n" % hd[0:8])
    f.write("  int t%s = (x_ ^ y) + 0x%s ;\n" % (hd, hd[8:16]))
    f.write("  x_ = t%s + vec%s[y&0x1fff] ;\n" % (hd, hd[0:8]))
    f.write("  int z%s = (y_ ^ (x_ - y)) - 0x%s ;\n" % (hd, hd[24:32]))
    f.write("  y_ = z%s ;\n" % hd)
    f.write("  return y_ + (x_ << 0x%s) ;\n" % hd[0])
    f.write("}\n")
  f.close()

  f = open("%susegen.cc" % fp, "w")
  f.write("#include \"%sgenerated.h\"\n" % fp)
  for ii in range(flag_num_classes):
    f.write("int %suseit%d(int x) { \n" % (cp, ii))
    f.write(" int rv = 0;\n")
    f.write("  %sKlass%d obj%d(x);\n" % (cp, ii, ii))
    f.write("  rv += obj%d.flarbit(x+%d);\n" % (ii, (ii*2+3)))
    f.write("  return rv;\n")
    f.write("}\n")
  f.close()


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options]

    options:
    -d    increase debug msg verbosity level
    -c N  emit N classes (def: 500)
    -C X  set class prefix to X
    -F Y  set file prefix to Y

    """ % os.path.basename(sys.argv[0])
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_num_classes, flag_class_prefix, flag_file_prefix

  try:
    optlist, args = getopt.getopt(sys.argv[1:], "dc:C:F:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))

  if args:
    usage("uknown extra args")
  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-c":
      flag_num_classes = int(arg)
    elif opt == "-C":
      flag_class_prefix = arg
    elif opt == "-F":
      flag_file_prefix = arg


# Setup
u.setdeflanglocale()
parse_args()

# Main guts
perform()
