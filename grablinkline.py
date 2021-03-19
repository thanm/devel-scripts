#!/usr/bin/python3
"""Filter to collect link link.

Reads stdin, collects and explodes link line.

"""

import re
import sys

import script_utils as u

#......................................................................

lines = sys.stdin.readlines()
recol = re.compile(r"^\s/.+/collect2\s+.+$")
reld = re.compile(r"^\s/.+/ld.gold\s+.+$")
found = False
for line in lines:
  if recol.match(line):
    chunks = line.split()
    for c in chunks:
      sys.stdout.write("%s\n" % c)
    found = True
    break
  if reld.match(line):
    chunks = line.split()
    for c in chunks:
      sys.stdout.write("%s\n" % c)
    found = True
    break
if not found:
  u.error("no link line found...")
