#!/usr/bin/python3
"""Read stdin, trim, and write stdout.

Read std input, then emit each line trimmed of leading/trailing whitespace.

"""

import sys

lines = sys.stdin.readlines()
for line in lines:
  sys.stdout.write("%s\n" % line.strip())
