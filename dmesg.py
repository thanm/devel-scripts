#!/usr/bin/python
"""Run 'dmesg' and post-process timestamps.

Runs 'dmesg' and then rewrite the contained timestamps
to make them human-readable.

"""

from datetime import datetime
from datetime import timedelta
import re
import script_utils as u


_datetime_format = "%Y-%m-%d %H:%M:%S"
_dmesg_line_regex = re.compile(r"^\[\s*(?P<time>\d+\.\d+)\](?P<line>.*)$")

#[  119.532141] init: log-sender-linhelm main process (7496) terminated with status 1

def human_dmesg():
  """Post-process dmesg output to yield human-readable dates."""
  now = datetime.now()
  uptime_diff = None
  try:
    with open("/proc/uptime") as f:
      uptime_diff = f.read().strip().split()[0]
  except IndexError:
    return
  try:
    uptime = now - timedelta(seconds=int(uptime_diff.split(".")[0]),
                             microseconds=int(uptime_diff.split(".")[1]))
    print "uptime is"
    print uptime
  except IndexError:
    return
  dmesg_data = u.docmdlines("dmesg")
  unmatched = 0
  matched = 0
  for line in dmesg_data:
    if not line:
      continue
    match = _dmesg_line_regex.match(line)
    if match:
      seconds = int(match.groupdict().get("time", "").split(".")[0])
      nanoseconds = int(match.groupdict().get("time", "").split(".")[1])
      microseconds = int(round(nanoseconds * 0.001))
      line = match.groupdict().get("line", "")
      t = uptime + timedelta(seconds=seconds, microseconds=microseconds)
      print "[%s]%s" % (t.strftime(_datetime_format), line)
      matched += 1
    else:
      unmatched += 1
  if unmatched > matched/2:
    print "matched %d unmatched %d" % (matched, unmatched)

# ---------main portion of script -------------

u.setdeflanglocale()
human_dmesg()
