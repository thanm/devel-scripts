#!/usr/bin/python
"""Filter to sort by human-readable size.

Reads stdin, sorts by first chunk (which is human-readable size).
Ex:

   5M
   1KB
   2GB

will be sorted as 1,2,5.

"""

import sys

import script_utils as u

#......................................................................

lines = sys.stdin.readlines()
tups = []
for line in lines:
  chunks = line.split()
  if chunks[0]:
    nbytes = u.hr_size_to_bytes(chunks[0])
    if not nbytes:
      continue
    tup = (nbytes, chunks[0], " ".join(chunks[1:]))
    tups.append(tup)
  else:
    u.warning("malformed 'du' output line %s" % line)

stups = sorted(tups)
for t in stups:
  print "%-10s %s" % (t[1], t[2])
