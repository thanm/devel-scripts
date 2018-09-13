#!/usr/bin/python
"""Filter out datestamps from -debug-pass=Executions output.

For filtering clang/llc/opt trace output.

"""

import re
import sys

import script_utils as u


# Setup
u.setdeflanglocale()

match1 = re.compile(r"^\[\d.+\]\s+0x\S+\s(.*)$")

# Read
lines = sys.stdin.readlines()
for line in lines:
  res1 = match1.match(line)
  if res1:
    rem = res1.group(1)
    sys.stdout.write("%s\n" % rem)
    continue
  sys.stdout.write(line)
