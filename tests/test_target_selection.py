import unittest
from pathlib import Path
from copy import deepcopy
from cokw_lore_sheets.config import validate
from cokw_lore_sheets.fixture import FixtureProvider
from cokw_lore_sheets.model import capture
from cokw_lore_sheets.checks import evaluate,summary_lines
from cokw_lore_sheets.listing import list_cells
ROOT=Path(__file__).resolve().parents[1]

class TwoStageTargetTests(unittest.TestCase):
    def setUp(self):
        self.cfg=validate({"checks":[{"name":"Imports","file_pattern":".*","sheet_pattern":"^IMP_",
                                    "range":"A1","test":"formula_matches","pattern":"IMPORTRANGE"}]})
        self.snap=capture(FixtureProvider(ROOT/"examples/fixture.example.json"),self.cfg)
        outside=deepcopy(self.snap["files"][0]);outside.update(id="no-imports",name="Other book")
        for sheet in outside["sheets"]:sheet["properties"]["title"]="Ordinary sheet"
        self.snap["files"].append(outside)

    def test_nonmatching_file_is_silent_in_check_list_and_summary(self):
        report=evaluate(self.snap,self.cfg)
        self.assertTrue(report["passed"])
        self.assertEqual(report["tested_cells"],1)
        self.assertEqual(len(summary_lines(self.snap,self.cfg,report)),1)
        listing=list_cells(self.snap,self.cfg)
        self.assertEqual(listing["issues"],[])
        self.assertEqual(len(listing["rows"]),1)

    def test_every_matching_sheet_is_checked(self):
        book=self.snap["files"][0]
        bad=deepcopy(book["sheets"][0]);bad["properties"].update(sheetId=99,title="IMP_Copied")
        bad["cells"]["A1"]["input"]={"stringValue":"copied value"}
        book["sheets"].append(bad)
        report=evaluate(self.snap,self.cfg)
        self.assertEqual(report["tested_cells"],2)
        self.assertFalse(report["passed"])
        self.assertEqual(report["failures"][0]["sheet_id"],99)
        lines=summary_lines(self.snap,self.cfg,report)
        self.assertEqual(sum(line.endswith(" OK") for line in lines),1)
        self.assertEqual(sum(line.endswith(" ERROR") for line in lines),1)
        self.assertEqual(len(list_cells(self.snap,self.cfg)["rows"]),2)

    def test_no_targets_anywhere_is_one_rule_error(self):
        self.snap["files"]=self.snap["files"][1:]
        report=evaluate(self.snap,self.cfg)
        self.assertFalse(report["passed"])
        self.assertEqual(len(report["failures"]),1)
        self.assertIsNone(report["failures"][0]["file_id"])
        self.assertEqual(len(list_cells(self.snap,self.cfg)["issues"]),1)
        self.assertEqual(summary_lines(self.snap,self.cfg,report),["Imports-^IMP_ ERROR"])
