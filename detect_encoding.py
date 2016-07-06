#!/usr/bin/python
"""Filter script to guess encoding (using chartdet pkg).

Reads from stdin, then uses 'chardet' to guess character encoding.

"""

import sys

import chardet

print "being reading stdin..."
rawdata = sys.stdin.read()
result = chardet.detect(rawdata)
charenc = result["encoding"]
print "...guessed encoding: %s" % charenc
