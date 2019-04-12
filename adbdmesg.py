#!/usr/bin/python3
"""Run 'dmesg' on connected device and post-process timestamps.

Runs 'dmesg' on the currently connected Android device and rewrites
the timesteps from the log to make them human-readable.

"""

from datetime import datetime
from datetime import timedelta
import re
import script_utils as u


_datetime_format = "%Y-%m-%d %H:%M:%S"
_dmesg_line_regex = re.compile(r"^\<\d+\>\[\s*(?P<time>\d+\.\d+)\]"
                               r"(?P<line>.*)$")
_dmesg_line_regex2 = re.compile(r"^\[\s*(?P<time>\d+\.\d+)\](?P<line>.*)$")


def device_now():
  """Return datetime object constructed from 'now' on device."""
  cmd = "adb shell date '+%Y:%m:%d:%H:%M:%S'"
  lines = u.docmdlines(cmd)
  line = lines.pop(0)
  if line is None:
    u.error("unable to interpret output from '%s'" % cmd)
  d = line.split(":")
  try:
    dt = datetime(int(d[0]), int(d[1]), int(d[2]),
                  int(d[3]), int(d[4]), int(d[5]))
    return dt
  except ValueError:
    u.error("unable to parse/interpret output "
            "from cmd '%s' (value %s)" % (cmd, line))


def human_dmesg(device_uptime):
  """Post-process dmesg output to yield human-readable dates."""
  now = device_now()
  uptime_diff = device_uptime

  try:
    uptime = now - timedelta(seconds=int(uptime_diff.split(".")[0]),
                             microseconds=int(uptime_diff.split(".")[1]))
  except IndexError:
    return

  # Dmesg output seems to be encoded in ISO-8859-2, which seems weird?
  # Force down to ASCII for now.
  dmesg_data = u.docmdbytes("adb shell dmesg")
  decoded_data = dmesg_data.decode("ASCII", "ignore")
  lines = decoded_data.splitlines()

  for line in lines:
    if not line:
      continue
    match = _dmesg_line_regex.match(line)
    if not match:
      match = _dmesg_line_regex2.match(line)
    if match:
      seconds = int(match.groupdict().get("time", "").split(".")[0])
      nanoseconds = int(match.groupdict().get("time", "").split(".")[1])
      microseconds = int(round(nanoseconds * 0.001))
      line = match.groupdict().get("line", "")
      t = uptime + timedelta(seconds=seconds, microseconds=microseconds)
      print("[%s]%s" % (t.strftime(_datetime_format), line))
    else:
      u.warning("unmatched line: %s" % line)

# ---------main portion of script -------------

u.setdeflanglocale()

# Check to make sure we can run adb
u.doscmd("which adb")

# Grab device uptime
dev_uptime = u.docmdlines("adb shell cat /proc/uptime").pop(0).split()[0]

# Execute
human_dmesg(dev_uptime)
