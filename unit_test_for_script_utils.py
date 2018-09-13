#!/usr/bin/python
"""Unit tests for script utils.

"""

import tempfile
import unittest
import sys

import script_utils as u


class TestScriptUtilsMethods(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    u.unit_test_enable()
    u.setdeflanglocale()

  def test_docmd_pass(self):
    u.docmd("/bin/true")

  def test_docmd_fail(self):
    with self.assertRaises(Exception):
      u.docmd("/bin/false")

  def test_docmdnf_pass(self):
    rc = u.docmdnf("/bin/true")
    self.assertTrue(rc == 0)

  def test_docmdnf_fail(self):
    rc = u.docmdnf("/bin/false")
    self.assertTrue(rc != 0)

  def test_doscmd_pass(self):
    u.doscmd("uname -a")

  def test_doscmd_fail(self):
    with self.assertRaises(Exception):
      u.doscmd("date -XYZ")

  def test_doscmd_fail_with_rc(self):
    rc = u.doscmd("/bin/false", True)
    self.assertTrue(rc != 0)

  def test_docmdout_pass(self):
    outf = tempfile.NamedTemporaryFile(mode="w", delete=True)
    u.docmdout("uname", outf.name)
    verif = open(outf.name, "r")
    lines = verif.readlines()
    verif.close()
    self.assertTrue(lines[0].strip() == "Linux")

  def test_docmdout_fail(self):
    with self.assertRaises(Exception):
      outf = tempfile.NamedTemporaryFile(mode="w", delete=True)
      u.docmdout("date -XYZ", outf.name)

  def test_docmdout_nf(self):
    val = u.docmdout("/bin/false", "/dev/null", True)
    self.assertTrue(val == None)

  def test_docmdinout_pass(self):
    outf = tempfile.NamedTemporaryFile(mode="w", delete=True)
    inf = tempfile.NamedTemporaryFile(mode="w", delete=True)
    inf.write("print 'foo'")
    inf.flush()
    rc = u.docmdinout("python", inf.name, outf.name)
    self.assertTrue(rc == 0)
    verif = open(outf.name, "r")
    lines = verif.readlines()
    verif.close()
    self.assertTrue(lines[0].strip() == "foo")

  def test_docmdinout_fail(self):
    outf = tempfile.NamedTemporaryFile(mode="w", delete=True)
    inf = tempfile.NamedTemporaryFile(mode="w", delete=True)
    inf.write("flarpish")
    inf.flush()
    rc = u.docmdinout("python -", inf.name, outf.name)
    self.assertTrue(rc != 0)

  def test_docmdlines_pass(self):
    lines = u.docmdlines("expr 2 + 5")
    self.assertTrue(lines[0].strip() == "7")

  def test_docmdlines_fail(self):
    with self.assertRaises(Exception):
      _ = u.docmdlines("expr glom blarch")

  def test_docmdbytes_pass(self):
    somebytes = u.docmdbytes("expr 2 + 5")
    self.assertTrue(somebytes[0] == b"7")

  def test_docmdbytes_fail(self):
    with self.assertRaises(Exception):
      _ = u.docmdbytes("expr glom blarch")

  def test_docmdbytes_fail_with_rc(self):
    rc = u.docmdbytes("/bin/false", True)
    self.assertFalse(rc == 0)

  def test_docmdinstring_pass(self):
    lines = u.docmdinstring("tr x y", "xxx")
    self.assertTrue(lines[0].strip() == "yyy")

  def test_docmdinstring_fail(self):
    with self.assertRaises(Exception):
      _ = u.docmdinstring("/bin/false", "xxx")

  def test_docmdwithtimeout_pass(self):
    rc = u.docmdwithtimeout("/bin/true", 2)
    self.assertTrue(rc == 0)

  def test_docmdwithtimeout_fail(self):
    rc = u.docmdwithtimeout("/bin/false", 2)
    self.assertTrue(rc > 0)

  def test_docmdwithtimeout_to(self):
    u.increment_verbosity()
    rc = u.docmdwithtimeout("sleep 99", 1)
    self.assertTrue(rc == -1)

  def test_ssdroot_pass(self):
    self.assertEqual(u.determine_btrfs_ssdroot("/ssd/tmp"), "/ssd")

  def test_ssdroot_fail(self):
    with self.assertRaises(Exception):
      _ = u.determine_btrfs_ssdroot("/tmp")

  def test_hr_size_convert(self):
    u.increment_verbosity()
    b1 = u.hr_size_to_bytes("1G")
    self.assertTrue(b1 == 1073741824)
    b2 = u.hr_size_to_bytes("1M")
    self.assertTrue(b2 == 1048576)
    b3 = u.hr_size_to_bytes("1.2M")
    self.assertTrue(b3 == 1258291)
    b4 = u.hr_size_to_bytes("glarp")
    self.assertTrue(b4 == None)
    b5 = u.hr_size_to_bytes("44Z")
    self.assertTrue(b5 == None)
    hr1 = u.bytes_to_hr_size(13)
    self.assertTrue(hr1 == "13 bytes")
    hr2 = u.bytes_to_hr_size(1057)
    self.assertTrue(hr2 == "1.0KB")
    hr3 = u.bytes_to_hr_size(7877879)
    self.assertTrue(hr3 == "7.5MB")
    hr4 = u.bytes_to_hr_size(97537877879)
    self.assertTrue(hr4 == "90.8GiB")

  def test_trim_perf_report(self):
    u.increment_verbosity()
    # Write a file that needs trimming
    outf = tempfile.NamedTemporaryFile(mode="w", delete=True)
    try:
      with open(outf.name, "w") as wf:
        wf.write("foo   \n")
    except IOError:
      u.verbose(0, "open failed for %s" % outf.name)
      self.assertTrue(1 == 0)
    # trim it
    u.trim_perf_report_file(outf.name)
    # verify it
    try:
      with open(outf.name, "r") as rf:
        lines = rf.readlines()
        self.assertTrue(len(lines) == 1)
        print "foo is: =%s=\n" % lines[0]
        self.assertTrue(lines[0] == "foo\n")
    except IOError:
      u.verbose(0, "re-open failed for %s" % outf.name)
      self.assertTrue(1 == 0)


if __name__ == "__main__":
  unittest.main()
