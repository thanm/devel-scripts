#!/usr/bin/python3
"""String canonicalizer module.

Helper class to record canonical strings. Methods:
 query(s): maps string "s" to ID or -1 if no mapping for string
 lookup(s): maps string "s" to ID, returns ID (mapping added if needed)
 getbyid(id): returns string for specified ID "id"

"""


class StringTable(object):
  """String table helper class."""

  def __init__(self, name):
    self.name = name
    self.stringtab = []
    self.stringdict = {}
    self.lookup("")

  def query(self, s):
    result = self.stringdict.get(s)
    if result:
      return result
    return -1

  def lookup(self, s):
    result = self.stringdict.get(s)
    if result:
      return result
    sid = len(self.stringtab)
    self.stringtab.append(s)
    self.stringdict[s] = sid
    return sid

  def getbyid(self, sid):
    if sid >= len(self.stringtab):
      raise Exception("StringTable '%s': invalid "
                      "string ID: %d" % (self.name, sid))
    return self.stringtab[sid]
