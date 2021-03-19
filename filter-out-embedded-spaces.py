#!/usr/bin/python3
"""Filter out input lines that have embedded spaces or quotes.

Read std input, filter out any line with embedded spaces or quotes. Intended to
screen out things that could cause problems with "ctags".

"""

import re
import sys

import script_utils as u


# Setup
u.setdeflanglocale()

match1 = re.compile(r"^.*[^\s]+\s+[^\s]+.*$")
match2 = re.compile(r"^.*[\'\"]+.*$")

# Read
lines = sys.stdin.readlines()
for line in lines:
  res1 = match1.match(line)
  if res1:
    continue
  res2 = match2.match(line)
  if res2:
    continue
  sys.stdout.write(line)
