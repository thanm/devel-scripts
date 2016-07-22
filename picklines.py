#!/usr/bin/python
"""Pick lines N through M of stdin."""

import sys

import script_utils as u

if len(sys.argv) != 3:
  u.error("args should be: LO HI")
try:
  stline = int(sys.argv[1])
  enline = int(sys.argv[2])
except ValueError:
  u.error("args should be numeric: LO HI")
if stline > enline:
  u.error("args should be numeric: LO HI where LO <= HI")
if stline < 1:
  u.error("args should be numeric: LO HI where LO >= 1")
lines = sys.stdin.readlines()
ll = len(lines)
if stline > ll:
  u.error("LO value %d greater than ll %d" % (stline, ll))
if enline > ll:
  u.error("EN value %d greater than ll %d" % (enline, ll))
for line in lines[stline-1:enline]:
  sys.stdout.write("%s\n" % line.strip())
