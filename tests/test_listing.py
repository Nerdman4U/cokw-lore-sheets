import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from cokw_lore_sheets.config import validate
from cokw_lore_sheets.fixture import FixtureProvider
from cokw_lore_sheets.model import capture, hashes
from cokw_lore_sheets.listing import list_cells, render
from cokw_lore_sheets.storage import write_json
from cokw_lore_sheets.cli import main

ROOT=Path(__file__).resolve().parents[1]
class ListingTests(unittest.TestCase):
    def setUp(self):
        self.config=validate({"checks":[{"name":"Inspect","sheet_pattern":"^IMP_","range":"A1:C1","test":"not_empty"}]})
        self.snapshot=capture(FixtureProvider(ROOT/"examples/fixture.example.json"),self.config)

    def test_blank_cells_and_formula_values(self):
        report=list_cells(self.snapshot,self.config)
        self.assertEqual([r["cell"] for r in report["rows"]],["A1","B1","C1"])
        self.assertIn("formulaValue",report["rows"][0]["input"])
        self.assertEqual(report["rows"][1]["input"],{})
        self.assertEqual(report["issues"],[])

    def test_overlapping_rules_are_labeled(self):
        cfg=deepcopy(self.config);cfg["checks"].append({**cfg["checks"][0],"name":"Second"})
        report=list_cells(self.snapshot,cfg)
        self.assertEqual(len(report["rows"]),6)
        self.assertEqual(report["rows"][-1]["check"],"Second")

    def test_missing_matches_empty_checks_and_limits(self):
        cfg=deepcopy(self.config);cfg["checks"][0]["file_pattern"]="^Absent$"
        self.assertIn("No captured files",list_cells(self.snapshot,cfg)["issues"][0]["reason"])
        cfg["checks"][0]["file_pattern"]=".*";cfg["checks"][0]["sheet_pattern"]="^Absent$"
        self.assertIn("No sheets",list_cells(self.snapshot,cfg)["issues"][0]["reason"])
        cfg["checks"]=[]
        self.assertIn("No checks",list_cells(self.snapshot,cfg)["issues"][0]["reason"])
        cfg=deepcopy(self.config);cfg["max_check_cells"]=1
        report=list_cells(self.snapshot,cfg)
        self.assertEqual(report["rows"],[])
        self.assertIn("exceeds",report["issues"][0]["reason"])

    def test_tsv_roundtrip_preserves_special_characters(self):
        report=list_cells(self.snapshot,self.config)
        report["rows"][0]["file_name"]="Name\twith\nline and \u00e4"
        text=render(report,"tsv")
        rows=list(csv.reader(io.StringIO(text),delimiter="\t"))
        self.assertEqual(rows[1][1],report["rows"][0]["file_name"])
        self.assertEqual(rows[1][6],report["rows"][0]["input"]["formulaValue"])
        self.assertEqual(json.loads(render(report,"json")),report)

    def test_missing_results_are_explicit(self):
        self.snapshot["include_results"]=False
        self.assertIsNone(list_cells(self.snapshot,self.config)["rows"][0]["result"])

    def call(self,args):
        out,err=io.StringIO(),io.StringIO()
        with redirect_stdout(out),redirect_stderr(err):code=main(args)
        return code,out.getvalue(),err.getvalue()

    def test_cli_no_baseline_required_and_output_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);snap=root/"snap.json";cfg=root/"config.json";dest=root/"report.tsv"
            write_json(snap,self.snapshot)
            raw={"files":{"folder_ids":["different-scope"]},"checks":[
                {"name":"Inspect","range":"A1","test":"unchanged"}]}
            write_json(cfg,raw)
            args=["list",str(snap),"--config",str(cfg)]
            code,out,err=self.call(args)
            self.assertEqual(code,0,err);self.assertIn("IMPORTRANGE",out)
            code,out,err=self.call(args+["--output",str(dest)])
            self.assertEqual(code,0,err);self.assertEqual(out,"")
            original=dest.read_bytes()
            self.assertEqual(self.call(args+["--output",str(dest)])[0],2)
            self.assertEqual(dest.read_bytes(),original)

    def test_cli_incomplete_and_tampered_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cfg=root/"cfg.json";snap=root/"snapshot.json"
            write_json(cfg,self.config)
            self.snapshot["complete"]=False;self.snapshot["errors"]=[{"error":"Read failed"}]
            write_json(snap,self.snapshot)
            code,out,err=self.call(["list",str(snap),"--config",str(cfg),"--format","json"])
            self.assertEqual(code,2);self.assertFalse(json.loads(out)["source_complete"])
            self.assertIn("incomplete",err)
            self.snapshot["files"][0]["name"]="tampered"
            altered=root/"altered.json";write_json(altered,self.snapshot)
            code,out,err=self.call(["list",str(altered),"--config",str(cfg)])
            self.assertEqual(code,2);self.assertIn("hash mismatch",err)
