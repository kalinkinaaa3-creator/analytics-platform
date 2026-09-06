"""Offline archive contract checks; PostgreSQL COPY is checked by --dry-run on the server."""
import csv
import io
import os
import unittest
from zipfile import ZipFile

os.environ["DJANGO_SETTINGS_MODULE"] = "tests.wordstat_settings"
import django
django.setup()

from django.core.management.base import CommandError
from datasets.management.commands.import_wordstat_regions import HEADER, archive_member


class ArchiveContractTests(unittest.TestCase):
    def archive(self, header, extra=False):
        content = io.StringIO(newline="")
        csv.writer(content).writerow(header)
        data = io.BytesIO()
        with ZipFile(data, "w") as archive:
            archive.writestr("region.csv", "\ufeff" + content.getvalue())
            if extra:
                archive.writestr("other.csv", content.getvalue())
        data.seek(0)
        return ZipFile(data)

    def test_accepts_exact_header_with_bom_without_extraction(self):
        with self.archive(HEADER) as archive:
            self.assertEqual(archive_member(archive).filename, "region.csv")

    def test_rejects_reordered_or_missing_columns(self):
        for header in (list(reversed(HEADER)), HEADER[:-1]):
            with self.archive(header) as archive, self.assertRaises(CommandError):
                archive_member(archive)

    def test_rejects_ambiguous_archive(self):
        with self.archive(HEADER, extra=True) as archive, self.assertRaises(CommandError):
            archive_member(archive)
