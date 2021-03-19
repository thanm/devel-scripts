#!/usr/bin/python3
"""Filter for obscuring hex addresses.

Filters out 'addresses' of the form 0x0000000007641700, replacing them
with anonymized tags of the form '0x<...>'. Useful for prepareing two
dump files for a diff.

"""

import re
import sys

import script_utils as u


# Setup
u.setdeflanglocale()

# Read
lines = sys.stdin.readlines()
for line in lines:
  xline = re.sub(r'0x[0-9a-f]+\S*', '0x<...>', line)
  sys.stdout.write(xline)
