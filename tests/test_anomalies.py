import unittest
from copy import deepcopy
from cokw_lore_sheets.anomalies import audit
from cokw_lore_sheets.config import validate
from cokw_lore_sheets.model import hashes, normalize
from cokw_lore_sheets.checks import evaluate, summary_lines


def snapshot(cells, **timings):
    return {"complete": True, "files": [{"id": "file", "name": "Synthetic book", "timings": {"transfer_ms": 1234},
        "sheets": [{"properties": {"sheetId": 1, "title": "Data", "gridProperties": {"rowCount": 10000, "columnCount": 5}},
                    "cells": cells, "timings": timings}]}]}


def cell(formula="=IF(A2=\"\",\"\",A2)", result=None):
    return {"input": {"formulaValue": formula}, "result": {} if result is None else result}


class AnomalyTests(unittest.TestCase):
    def test_imp_spill_is_not_hundreds_of_formulas(self):
        cells = {"A1": cell("=IMPORTRANGE(\"id\",\"A1:B2000\")", {"stringValue": "Header"})}
        cells.update({f"A{i}": {"input": {}, "result": {"numberValue": i}} for i in range(2, 2001)})
        report = audit(snapshot(cells), {})
        self.assertEqual(report["warning_count"], 0)
        self.assertEqual(report["sheets"][0]["formula_cells"], 1)
        self.assertEqual(report["sheets"][0]["last_result_row"], 2000)

    def test_formula_tail_reports_exact_ranges_but_never_claims_safe_deletion(self):
        cells = {"A20": {"input": {"stringValue": "Last record"}}}
        cells.update({f"B{i}": cell() for i in range(21, 1501)})
        report = audit(snapshot(cells), {})
        tail = next(w for w in report["warnings"] if w["kind"] == "blank_formula_tail")
        self.assertEqual(tail["ranges"], ["B21:B1500"])
        self.assertFalse(tail["automatic_deletion_safe"])

    def test_zero_false_and_errors_are_not_blank_results(self):
        for result in ({"numberValue": 0}, {"boolValue": False}, {"errorValue": {"type": "REF"}}, {"stringValue": "#REF!"}):
            cells = {f"B{i}": cell(result=result) for i in range(1, 150)}
            self.assertFalse(any(w["kind"] == "blank_formula_tail" for w in audit(snapshot(cells), {})["warnings"]))

    def test_missing_result_cannot_be_called_blank(self):
        cells = {f"B{i}": {"input": {"formulaValue": "=1"}} for i in range(1, 150)}
        self.assertEqual(audit(snapshot(cells), {})["warning_count"], 0)

    def test_unused_grid_rows_alone_are_not_suspicious(self):
        self.assertEqual(audit(snapshot({"B20": cell()}), {})["warning_count"], 0)

    def test_configured_thresholds_and_disable(self):
        snap = snapshot({"B101": cell()})
        cfg = validate({"anomalies": {"rules": [{"file_pattern": "Synthetic", "sheet_pattern": "^Data$", "max_formula_row": 100}]}})
        self.assertEqual(audit(snap, cfg)["warning_count"], 1)
        self.assertEqual(audit(snap, validate({"anomalies": {"enabled": False}}))["warning_count"], 0)

    def test_reports_every_sheet_without_fabricating_load_time(self):
        snap = snapshot({}, load_ms=400, load_measurement="server-side")
        second = deepcopy(snap["files"][0]["sheets"][0]);second["properties"]["sheetId"] = 2;second.pop("timings")
        snap["files"][0]["sheets"].append(second)
        report = audit(snap, {}, {("file", 1): 12})
        self.assertEqual(len(report["sheets"]), 2)
        self.assertEqual(report["sheets"][0]["load_ms"], 400)
        self.assertGreaterEqual(report["sheets"][0]["check_ms"], 12)
        self.assertEqual(report["sheets"][0]["workbook_transfer_ms"], 1234)
        self.assertIsNone(report["sheets"][1]["load_ms"])

    def test_warning_is_visible_in_check_status_without_a_snapshot_diff(self):
        snap = snapshot({"B1001": cell()})
        cfg = validate({"checks": [{"name": "Data", "test": "formula_matches", "range": "B1001", "pattern": "IF"}]})
        report = evaluate(snap, cfg)
        self.assertFalse(report["passed"])
        self.assertTrue(any("WARNING" in line for line in summary_lines(snap, cfg, report)))

    def test_timings_do_not_affect_hashes(self):
        book = {"id": "file", "name": "Test", "parents": [], "properties": {}, "named_ranges": [],
                "sheets": snapshot({})["files"][0]["sheets"]}
        before = hashes(book)
        book["timings"] = {"transfer_ms": 10000}
        book["sheets"][0]["timings"] = {"load_ms": 999}
        self.assertEqual(hashes(book), before)

    def test_normalize_keeps_measured_server_time_outside_properties(self):
        raw = {"spreadsheetId": "file", "sheets": [{"properties": {"sheetId": 1, "title": "Data", "gridProperties": {"rowCount": 1, "columnCount": 1}},
               "capture_timings": {"load_ms": 123, "load_measurement": "server-side"}, "data": []}]}
        sheet = normalize({"id": "file", "name": "Synthetic"}, raw, validate({}))["sheets"][0]
        self.assertEqual(sheet["timings"]["load_ms"], 123)
        self.assertGreaterEqual(sheet["timings"]["normalize_ms"], 0)
        self.assertNotIn("timings", sheet["properties"])

    def test_invalid_anomaly_configuration_fails_before_network(self):
        for raw in ({"max_formula_row": 0}, {"enabled": "yes"}, {"rules": [{"file_pattern": "["}]}):
            with self.assertRaises(ValueError):
                validate({"anomalies": raw})

    def test_partial_capture_is_labelled_in_the_report(self):
        snap = snapshot({});snap["complete"] = False
        self.assertFalse(audit(snap, {})["source_complete"])
