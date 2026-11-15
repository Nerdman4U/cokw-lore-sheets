"""Read adapter behavior with synthetic API responses and no network."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cokw_lore_sheets.google import GoogleProvider
from cokw_lore_sheets.config import validate


class GoogleAdapterTests(unittest.TestCase):
    def setUp(self):
        self.provider = GoogleProvider.__new__(GoogleProvider)
        self.provider.drive = Mock()
        self.provider.sheets = Mock()
        self.provider.account_id = "synthetic-account"
        self.config = validate({})
        self.meta = {"spreadsheetId": "synthetic-id", "sheets": [
            {"properties": {"sheetId": 0, "title": "Data",
                            "gridProperties": {"rowCount": 4, "columnCount": 3}}}]}

    def test_all_drive_pages_are_read(self):
        self.provider.drive.files().list().execute.side_effect = [
            {"files": [{"id": "one"}], "nextPageToken": "page-two"},
            {"files": [{"id": "two"}]}]
        self.assertEqual([f["id"] for f in self.provider.list_files(self.config["files"])],
                         ["one", "two"])
        calls = [c for c in self.provider.drive.files().list.call_args_list if "q" in c.kwargs]
        self.assertIsNone(calls[0].kwargs["pageToken"])
        self.assertEqual(calls[1].kwargs["pageToken"], "page-two")
        self.assertIn("'me' in owners", calls[0].kwargs["q"])

    def test_incomplete_search_is_not_a_complete_empty_catalog(self):
        self.provider.drive.files().list().execute.return_value = {"incompleteSearch": True}
        with self.assertRaisesRegex(ValueError, "incomplete search"):
            self.provider.list_files(self.config["files"])

    def test_repeated_page_token_is_rejected(self):
        self.provider.drive.files().list().execute.return_value = {"nextPageToken": "same"}
        with self.assertRaisesRegex(ValueError, "repeated page"):
            self.provider.list_files(self.config["files"])

    def test_edits_during_read_are_retried(self):
        get = self.provider.drive.files().get().execute
        get.side_effect = [{"version": "1"}, {"version": "2"},
                           {"version": "2"}, {"version": "2"}]
        self.provider.sheets.spreadsheets().get().execute.side_effect = [
            self.meta, self.meta, self.meta, self.meta]
        metadata, raw = self.provider.fetch({"id": "synthetic-id"}, self.config)
        self.assertEqual(metadata["version"], "2")
        self.assertEqual(raw["spreadsheetId"], "synthetic-id")
        self.assertEqual(get.call_count, 4)
        fields = self.provider.sheets.spreadsheets().get.call_args.kwargs["fields"]
        self.assertEqual(fields.count("sheets("), 1)
        self.assertIn("userEnteredValue,effectiveValue", fields)
        self.assertEqual(fields.count("("), fields.count(")"))

    def test_persistent_edits_never_get_a_hash(self):
        self.provider.drive.files().get().execute.side_effect = [
            {"version": str(i)} for i in range(6)]
        self.provider.sheets.spreadsheets().get().execute.return_value = self.meta
        with self.assertRaisesRegex(ValueError, "all three"):
            self.provider.fetch({"id": "synthetic-id"}, self.config)

    def test_grid_limit_is_checked_before_cells_are_requested(self):
        cfg = validate({"max_cells_per_sheet": 2})
        self.provider.drive.files().get().execute.return_value = {"version": "1"}
        self.provider.sheets.spreadsheets().get().execute.return_value = self.meta
        with self.assertRaisesRegex(ValueError, "max_cells_per_sheet"):
            self.provider.fetch({"id": "synthetic-id"}, cfg)
        self.assertEqual(self.provider.sheets.spreadsheets().get().execute.call_count, 1)


if __name__ == "__main__":
    unittest.main()
