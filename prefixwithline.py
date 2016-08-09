#!/usr/bin/python
"""Read stdin, output same with line prefix line numbers.

Read std input, then emit each line tagged with its line number.

"""

import math
import sys

lines = sys.stdin.readlines()
lten = int(math.log(len(lines), 10)) + 1
count = 0
for line in lines:
  count += 1
  sys.stdout.write("%0*d: %s" % (lten, count, line))
