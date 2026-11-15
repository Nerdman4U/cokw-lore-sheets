"""Synthetic behavioral tests; no Google credentials or network required."""
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cokw_lore_sheets.config import validate, bounds
from cokw_lore_sheets.model import capture, hashes
from cokw_lore_sheets.checks import evaluate
from cokw_lore_sheets.compare import compare
from cokw_lore_sheets.fixture import FixtureProvider
from cokw_lore_sheets.storage import load_json, write_json, save_token
from cokw_lore_sheets.cli import main

ROOT = Path(__file__).resolve().parents[1]


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.config = validate(load_json(ROOT / "examples/config.example.json"))
        self.provider = FixtureProvider(ROOT / "examples/fixture.example.json")
        self.snapshot = capture(self.provider, self.config)

    def mutate(self, action):
        result = deepcopy(self.snapshot)
        action(result["files"][0])
        result["files"][0]["hashes"] = hashes(result["files"][0])
        return result

    def test_exact_row_relative_formulas_are_independent(self):
        cells = self.snapshot["files"][0]["sheets"][0]["cells"]
        self.assertEqual(cells["B2"]["input"], {"formulaValue": "=A2*2"})
        self.assertEqual(cells["B3"]["input"], {"formulaValue": "=A3*2"})
        after = self.mutate(lambda f: f["sheets"][0]["cells"]["B3"].update(input={"formulaValue": "=A2*2"}))
        edits = [r for r in compare(self.snapshot, after)["changes"] if r["kind"] == "cell_input_changed"]
        self.assertEqual([r["cell"] for r in edits], ["B3"])
        self.assertEqual(edits[0]["before"], {"formulaValue": "=A3*2"})

    def test_no_change_despite_timestamps_and_drive_version(self):
        after = self.mutate(lambda f: f.update(drive_version="99", modified_time="later"))
        after["created_at"] = "another capture time"
        self.assertFalse(compare(self.snapshot, after)["has_changes"])

    def test_result_changes_are_separate_from_input_changes(self):
        after = self.mutate(lambda f: f["sheets"][0]["cells"]["A1"].update(result={"numberValue": 999}))
        self.assertFalse(compare(self.snapshot, after)["has_changes"])
        self.assertEqual(len(compare(self.snapshot, after)["result_hash_changes"]), 1)
        self.assertTrue(compare(self.snapshot, after, True)["has_changes"])
        self.assertEqual(self.snapshot["files"][0]["hashes"]["content_sha256"],
                         after["files"][0]["hashes"]["content_sha256"])

    def test_rename_is_not_deletion(self):
        after = self.mutate(lambda f: (f.update(name="Renamed"),
                                      f["sheets"][0]["properties"].update(title="Renamed tab")))
        kinds = {r["kind"] for r in compare(self.snapshot, after)["changes"]}
        self.assertIn("sheet_metadata_changed", kinds)
        self.assertNotIn("file_removed", kinds)
        self.assertNotIn("sheet_removed", kinds)

    def test_removed_file_and_sheet_are_reported(self):
        after = deepcopy(self.snapshot); after["files"] = []
        self.assertEqual(compare(self.snapshot, after)["changes"][0]["kind"], "file_removed")
        after = self.mutate(lambda f: f.update(sheets=[]))
        self.assertIn("sheet_removed", [r["kind"] for r in compare(self.snapshot, after)["changes"]])

    def test_literal_replaces_formula(self):
        after = self.mutate(lambda f: f["sheets"][0]["cells"]["B2"].update(input={"numberValue": 6}))
        self.assertTrue(any(r.get("cell") == "B2" for r in compare(self.snapshot, after)["changes"]))

    def test_import_formula_and_error_are_distinct_tests(self):
        bad = self.mutate(lambda f: f["sheets"][0]["cells"]["A1"].update(
            result={"errorValue": {"type": "REF", "message": "Synthetic import access error"}}))
        report = evaluate(bad, self.config)
        self.assertEqual(len(report["failures"]), 1)
        self.assertEqual(report["failures"][0]["check"], "Import has no calculation error")

    def test_blank_cells_in_a_range_are_actually_checked(self):
        config = validate({"checks": [{"name": "No blanks", "range": "A1:C1", "test": "not_empty"}]})
        report = evaluate(self.snapshot, config)
        self.assertEqual(report["tested_cells"], 3)
        self.assertEqual({r["cell"] for r in report["failures"]}, {"B1", "C1"})

    def test_missing_sheet_and_file_matches_are_failures(self):
        cfg = deepcopy(self.config); cfg["checks"][0]["sheet_pattern"] = "^Absent$"
        self.assertIn("No sheets", evaluate(self.snapshot, cfg)["failures"][0]["reason"])
        cfg["checks"][0]["file_pattern"] = "^Absent$"
        self.assertIn("No captured files", evaluate(self.snapshot, cfg)["failures"][0]["reason"])

    def test_whole_columns_open_ranges_and_limits(self):
        self.assertEqual(bounds("B2:C3", 10, 3), (2, 2, 3, 3))
        self.assertEqual(bounds("A:A", 10, 3), (1, 1, 10, 1))
        self.assertEqual(bounds("2:3", 10, 3), (2, 1, 3, 3))
        self.assertEqual(bounds("B2:B", 10, 3), (2, 2, 10, 2))
        cfg = validate({"max_check_cells": 2, "checks": [
            {"name": "Bounded", "range": "A:A", "test": "not_empty"}]})
        self.assertIn("max_check_cells", evaluate(self.snapshot, cfg)["failures"][0]["reason"])

    def test_bad_config_is_rejected_before_google_access(self):
        for raw in [
            {"unknown": True},
            {"files": {"name_pattern": "["}},
            {"checks": [{"name": "bad", "range": "A1:B0", "test": "not_empty"}]},
            {"checks": [{"name": "bad", "test": "eval"}]},
            {"checks": [{"name": "bad", "test": "formula_matches"}]},
            {"include_results": False, "checks": [{"name": "bad", "test": "no_error"}]},
            {"max_check_cells": True}
        ]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                validate(raw)

    def test_unchanged_compares_by_sheet_id_after_rename(self):
        cfg = validate({"checks": [{"name": "Stable", "range": "B2:B3", "test": "unchanged"}]})
        after = self.mutate(lambda f: f["sheets"][0]["properties"].update(title="New name"))
        self.assertTrue(evaluate(after, cfg, self.snapshot)["passed"])
        self.assertFalse(evaluate(after, cfg)["passed"])

    def test_value_matches_false_and_zero_are_not_empty(self):
        cfg = validate({"checks": [{"name": "Zero", "range": "A1", "test": "value_matches", "pattern": "^0$"}]})
        after = self.mutate(lambda f: f["sheets"][0]["cells"]["A1"].update(result={"numberValue": 0}))
        self.assertTrue(evaluate(after, cfg)["passed"])
        cfg = validate({"checks": [{"name": "Entered", "range": "A1", "test": "not_empty"}]})
        after = self.mutate(lambda f: f["sheets"][0]["cells"]["A1"].update(input={"boolValue": False}))
        self.assertTrue(evaluate(after, cfg)["passed"])

    def test_hash_mismatch_rejected(self):
        forged = deepcopy(self.snapshot)
        forged["files"][0]["sheets"][0]["cells"]["B2"]["input"]["formulaValue"] = "=99"
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            compare(self.snapshot, forged)

    def test_hash_stable_under_dictionary_order(self):
        book = self.snapshot["files"][0]
        reordered = json.loads(json.dumps(book, sort_keys=True))
        self.assertEqual(hashes(book), hashes(reordered))

    def test_incomplete_read_never_becomes_a_deletion_report(self):
        self.provider.fixture["files"][0]["error"] = True
        partial = capture(self.provider, self.config)
        self.assertFalse(partial["complete"])
        self.assertEqual(partial["errors"][0]["file_id"], "synthetic-book")
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            compare(self.snapshot, partial)

    def test_scope_and_account_changes_rejected(self):
        for key, value in [("account_id", "other"), ("selection", {}),
                           ("include_results", False)]:
            after = deepcopy(self.snapshot); after[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                compare(self.snapshot, after)

    def test_grid_limit_and_configured_missing_file_make_capture_incomplete(self):
        cfg = validate({"max_cells_per_sheet": 1})
        self.assertFalse(capture(self.provider, cfg)["complete"])
        cfg = validate({"files": {"file_ids": ["missing-id"]}})
        self.assertFalse(capture(self.provider, cfg)["complete"])

    def test_sparse_offsets_and_empty_cells(self):
        raw = self.provider.fixture["files"][0]["spreadsheet"]["sheets"][0]
        raw["data"] = [{"startRow": 4, "startColumn": 1,
                        "rowData": [{"values": [{}, {"userEnteredValue": {"numberValue": 7}}]}]}]
        snap = capture(self.provider, self.config)
        self.assertEqual(list(snap["files"][0]["sheets"][0]["cells"]), ["C5"])

    def test_json_never_overwrites_and_tokens_cannot_be_in_git(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "snapshot.json"
            write_json(p, self.snapshot)
            with self.assertRaises(FileExistsError):
                write_json(p, {})
            self.assertEqual(load_json(p), self.snapshot)
            (Path(temp) / ".git").mkdir()
            with self.assertRaisesRegex(ValueError, "outside Git"):
                save_token(Path(temp) / "token.json", "{}")

    def test_cli_offline_dump_compare_check_and_failure_exit_codes(self):
        with tempfile.TemporaryDirectory() as temp, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            a, b = Path(temp)/"evening.json", Path(temp)/"morning.json"
            args = ["dump", "--config", str(ROOT/"examples/config.example.json"),
                    "--fixture", str(ROOT/"examples/fixture.example.json")]
            self.assertEqual(main([*args, "--output", str(a)]), 0)
            self.assertEqual(main([*args, "--output", str(b)]), 0)
            self.assertEqual(main(["compare", str(a), str(b)]), 0)
            self.assertEqual(main(["check", str(a), "--config", str(ROOT/"examples/config.example.json")]), 0)
            self.assertEqual(main([*args, "--output", str(a)]), 2)
            changed = self.mutate(lambda f: f["sheets"][0]["cells"]["B3"].update(input={"formulaValue": "=0"}))
            c = Path(temp)/"changed.json"; write_json(c, changed)
            self.assertEqual(main(["compare", str(a), str(c)]), 1)


if __name__ == "__main__":
    unittest.main()
