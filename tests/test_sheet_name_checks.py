import unittest
from cokw_lore_sheets.config import validate
from cokw_lore_sheets.checks import evaluate,summary_lines
from cokw_lore_sheets.listing import list_cells,render

class SheetNameChecks(unittest.TestCase):
    def setUp(self):
        self.raw={"include_results":False,"checks":[{"name":"Naming","sheet_pattern":"^IMP_",
                    "test":"sheet_name_matches","pattern":"^IMP_[A-Z]+$"}]}
        self.snap={"complete":True,"include_results":False,"files":[{"id":"one","name":"Book","sheets":[
            {"properties":{"sheetId":0,"title":"IMP_GOOD"}},
            {"properties":{"sheetId":1,"title":"IMP_bad"}},
            {"properties":{"sheetId":2,"title":"Ordinary"}}]}]}

    def test_names_evaluated_without_grid_cells_or_results(self):
        cfg=validate(self.raw);report=evaluate(self.snap,cfg)
        self.assertEqual(report["tested_cells"],2)
        self.assertEqual(len(report["failures"]),1)
        self.assertEqual(report["failures"][0]["sheet_name"],"IMP_bad")
        self.assertIsNone(report["failures"][0]["cell"])
        self.assertEqual(set(summary_lines(self.snap,cfg,report)),{"Book-IMP_GOOD OK","Book-IMP_bad ERROR"})

    def test_listing_contains_names_instead_of_cell_values(self):
        report=list_cells(self.snap,validate(self.raw))
        self.assertEqual(len(report["rows"]),2)
        for row in report["rows"]:
            self.assertIsNone(row["cell"])
            self.assertEqual(row["target"],"sheet_name")
            self.assertEqual(row["input"],{"stringValue":row["sheet_name"]})
            self.assertIsNone(row["result"])
        self.assertIn("IMP_GOOD",render(report,"tsv"))

    def test_pattern_required_and_validated(self):
        del self.raw["checks"][0]["pattern"]
        with self.assertRaises(ValueError):validate(self.raw)
        self.raw["checks"][0]["pattern"]="["
        with self.assertRaises(ValueError):validate(self.raw)

    def test_nonmatching_names_are_not_selected(self):
        self.raw["checks"][0]["sheet_pattern"]="^IMP_GOOD$"
        report=evaluate(self.snap,validate(self.raw))
        self.assertTrue(report["passed"])
        self.assertEqual(report["tested_cells"],1)
