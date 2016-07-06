#!/usr/bin/python
"""Manage downloading of AOSP blobs.

This script scrapes the contents of the Google web page that tracks
current versions of vendor blobs for AOSP images.  It then downloads
the most recent blobs for the most common development devices
into a repository where they can be picked up later on and incorporated
into an AOSP client.

More detailed background info:

Android system images built from AOSP clients can't be flashed
directly to Nexus devices without the incorporation of so-called
'vendor blobs' -- precompiled drivers or shared libraries containing
vendor-proprietary code. It is the responsibility of the developer to
select the correct blob(s) and install them into an Android repo
client once the client has been created. This process is annoying
(lots of searching, clicking, typing "yes I accept" etc) and is
vulnerable to user error. In addition, new blobs are posted every
couple of weeks. Google publishes links to vendor blobs on a public
web page:

  https://developers.google.com/android/nexus/blobs-preview

While the links to the actual blobs referred to om this web page change,
the rest of the page structures stays pretty much the same, meaning that
it's not hard to write something to scrape the page, locate the blobs,
and download them (hence the creation of this script).

See also 'install-aosp-blobs.py', which installs the correct set of
blobs in a client based on a device tag (ex: N5, N9, etc)

"""

import getopt
import os
import re
import sys

from lxml import html
import requests
import script_utils as u

#......................................................................

# Where to put blobs once we've downloaded them
flag_archive_dir = None

# What page to scrape to figure out what to download
flag_scrape_target = "https://developers.google.com/android/nexus/blobs-preview"

# Devices that we're interested in. Key is the tag we'll use to
# refer to the device; description is the raw text that we look
# for when scraping the blobs page
device_tags = {
    # "N5": "Nexus 5 (GSM/LTE) (hammerhead) binaries for Android",
    "N6": "Nexus 6 (Mobile) (shamu) binaries for Android",
    "fugu": "Nexus Player (fugu) binaries for Android",
    # "N7": "Nexus 7 (Wi-Fi) (flo) binaries for Android",
    "N9": "Nexus 9 (flounder) binaries for Android",
    }


def download_blob(device, version, link):
  """Download a specific blob."""

  # create location if needed
  devdir = "%s/%d" % (flag_archive_dir, version)
  if not os.path.isdir(devdir):
    os.mkdir(devdir)
  verdir = "%s/%s/%s" % (flag_archive_dir, version, device)
  if not os.path.isdir(verdir):
    os.mkdir(verdir)

  # download file
  base = os.path.basename(link)
  path = "%s/%s" % (verdir, base)
  if not os.path.exists(path):
    print "... downloading %s => %s" % (link, path)
    u.docmd("curl -L %s -o %s" % (link, path))
  else:
    print "... skipping %s blob %s (exists in archive already)" % (device, link)

  # Update current version link
  curlink = "%s/cur" % flag_archive_dir
  if os.path.exists(curlink):
    try:
      os.remove(curlink)
    except OSError as err:
      u.error("unable to remove current version "
              "link %s: %s" % (curlink, err))
  try:
    os.symlink("%d" % version, "%s/cur" % flag_archive_dir)
  except OSError as err:
    u.error("unable to update current version link %s" % curlink)


def postprocess(scraper):
  """Postprocess contents of scraped target web page."""
  if u.verbosity_level() > 0:
    sys.stderr.write("dump of scraper state\n")
    scraper.dump()
  blobtable = scraper.blobtable()
  version = scraper.version()
  for device, rows in blobtable.iteritems():
    idx = 0
    for r in rows:
      u.verbose(1, "device=%s idx=%d blob=%s\n" % (device, idx, r[2]))
      download_blob(device, version, r[2])


def usage(msgarg):
  """Print usage and exit."""
  if msgarg:
    sys.stderr.write("error: %s\n" % msgarg)
  print """\
    usage:  %s [options]

    options:
    -a D  store downloaded blobs in archive dir D (def: /ssd/blobs)
    -s T  set scrape target to T (def: %s)
    -d    increase debug trace level

    Downloads blobs from

      https://developers.google.com/android/nexus/blobs-preview

    and stores them in archive dir for future use.

    """ % (os.path.basename(sys.argv[0]), flag_scrape_target)
  sys.exit(1)


def parse_args():
  """Command line argument parsing."""
  global flag_archive_dir, flag_scrape_target
  try:
    optlist, args = getopt.getopt(sys.argv[1:], "da:s:")
  except getopt.GetoptError as err:
    # unrecognized option
    usage(str(err))
  if args:
    usage("unexpected extra args")

  for opt, arg in optlist:
    if opt == "-d":
      u.increment_verbosity()
    elif opt == "-a":
      flag_archive_dir = arg
    elif opt == "-s":
      flag_scrape_target = arg

  # Use $HOME/aosp_blobs if -a not specified
  if not flag_archive_dir:
    homedir = os.getenv("HOME")
    if not homedir:
      u.error("no setting for $HOME environment variable -- cannot continue")
    flag_archive_dir = "%s/blobs" % homedir
    sys.stderr.write("... archive dir not specified, "
                     "using %s\n" % flag_archive_dir)

  # Does archive dir exist?
  if os.path.exists(flag_archive_dir):
    # Error if not a directory
    if not os.path.isdir(flag_archive_dir):
      u.error("specified archive dir %s is "
              "not a directory" % flag_archive_dir)
  else:
    sys.stderr.write("... creating %s, since it "
                     "does not exist" % flag_archive_dir)
    try:
      os.mkdir(flag_archive_dir)
    except OSError as err:
      u.error("unable to create archive directory")

  u.verbose(0, "... archive dir: '%s'" % flag_archive_dir)
  u.verbose(0, "... scrape target: '%s'" % flag_scrape_target)


class NexusBlobPageScraper(object):
  """Helper class for scraping the Google Nexus vendor blobs page."""

  def __init__(self, scrape_target, dev_tags):
    self._scrape_target = scrape_target
    self._device_tags = dev_tags
    self._blobtable = {}
    self._version = -1

  def doit(self):
    """Top level method for scraper."""

    # Suck in the web page
    page = requests.get(self._scrape_target)
    tree = html.fromstring(page.text)

    # We're interested in the portions of the page containing
    # blob tables. See below for an example. We'll key off the
    # specific h3 text, then pick up the table that immediately
    # follows it.

    # Example:
    #
    # <h3>Nexus 7 (Mobile) (deb) binaries for Android (1856853)</h3>
    #
    # <table>
    #   <tr>
    #     <th>Hardware Component
    #     <th>Company
    #     <th>Download
    #     <th>MD5 Checksum
    #     <th>SHA-1 Checksum
    #   <tr>
    #     <td>Audio, Sensors
    #     <td>ASUS
    #     <td><a href="https://dl.google.com/...efb23bef.tgz">Link</a>
    #     <td>d15eb9e73a7706743eaa0d580880dafe
    #     <td>ac5b1c1d6234a942dc4883888d15e829dee3c749
    #   <tr>
    #     <td>NFC
    #     <td>Broadcom
    #     <td><a href="https://dl.google.com/...3-766ef5bf.tgz">Link</a>
    #     <td>1861ef5a58d9fd22768d088f09599842
    #     <td>fda601548b96e3fe8f956eb7f95531d54155cc9d
    #  ...
    # </table>
    #

    for tag, device_desc in self._device_tags.iteritems():
      self._scrape_version(tag, device_desc, tree)
      self._scrape_blobs(tag, device_desc, tree)

  def version(self):
    return self._version

  def blobtable(self):

    assert self._version > 0, ("no version recorded -- "
                               "scrape failed (or not run)")
    return self._blobtable

  def dump(self):
    sys.stderr.write("version: %d\n" % self._version)
    for tag, rowlist in self._blobtable.iteritems():
      idx = 0
      print "\nDevice %s:" % tag
      for r in rowlist:
        columns = " ".join(r)
        print "%d: %s" % (idx, columns)
        idx += 1

  def _scrape_version(self, tag, device_desc, tree):
    """Collect the version number for the blob of interest."""
    # Pick out the h3 text itself, since we need to use a pattern match
    # to collect the version (which changes periodically)
    xpath_query_h3 = "//*[contains(text(),'%s')]" % device_desc
    heading = tree.xpath(xpath_query_h3)
    heading_text = heading[0].text
    matcher = re.compile(r"^\s*(.+)\s+\((\d+)\)\s*$")
    m = matcher.match(heading_text)
    if m is None:
      u.error("internal error: h3 pattern match "
              "failed for %s: text is %s" % tag, heading_text)
    tagver = int(m.group(2))
    if self._version < 0:
      self._version = tagver
    elif tagver != self._version:
      u.error("blobs page has unexpected multiple "
              "versions (%d and %d) -- not sure if this matters")

  def _scrape_blobs(self, tag, device_desc, tree):
    """Scrape blobs of interest."""
    # Scoop up the contents of the table that immediately
    # follows the heading of interest
    xpath_query_table = ("//*[contains(text(),'%s')]"
                         "/following-sibling::table[1]" % device_desc)
    table = tree.xpath(xpath_query_table)
    table_rows = table[0]
    interesting_rows = table_rows[1:]
    rowlist = []
    for row in interesting_rows:
      desc = row[0].text_content().strip()
      company = row[1].text_content().strip()
      # text content for the download link is just the string "Link"
      # download_link = row[2].text_content().strip()
      link_child = row[2].xpath("child::a/@href")
      link_target = link_child[0].strip()
      md5sum = row[3].text_content().strip()
      sha1sum = row[4].text_content().strip()
      columnlist = [desc, company, link_target, md5sum, sha1sum]
      rowlist.append(columnlist)
    self._blobtable[tag] = rowlist


#
#----------------------------------------------------------------------
# Main portion of script
#

parse_args()
bscraper = NexusBlobPageScraper(flag_scrape_target, device_tags)
bscraper.doit()
postprocess(bscraper)
