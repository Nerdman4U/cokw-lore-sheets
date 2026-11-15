import io
import tempfile
import unittest
from pathlib import Path
from copy import deepcopy
from contextlib import redirect_stdout,redirect_stderr
from cokw_lore_sheets.config import validate
from cokw_lore_sheets.fixture import FixtureProvider
from cokw_lore_sheets.model import capture,hashes
from cokw_lore_sheets.checks import evaluate,summary_lines
from cokw_lore_sheets.cli import main
from cokw_lore_sheets.storage import write_json
ROOT=Path(__file__).resolve().parents[1]

class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.cfg=validate({"checks":[{"name":"Present","range":"A1","test":"not_empty"},
                                    {"name":"Formula","range":"A1","test":"formula_matches","pattern":"IMPORTRANGE"}]})
        self.snap=capture(FixtureProvider(ROOT/"examples/fixture.example.json"),self.cfg)

    def lines(self,cfg=None):
        cfg=cfg or self.cfg
        return summary_lines(self.snap,cfg,evaluate(self.snap,cfg))

    def test_checks_group_into_one_ok_line(self):
        lines=self.lines();self.assertEqual(len(lines),1)
        self.assertTrue(lines[0].endswith(" OK"))

    def test_one_failed_check_causes_error(self):
        self.snap["files"][0]["sheets"][0]["cells"]["A1"]["input"]={"stringValue":"copied data"}
        self.assertTrue(self.lines()[0].endswith(" ERROR"))

    def test_missing_targets_and_empty_checks(self):
        cfg=deepcopy(self.cfg);cfg["checks"][0]["sheet_pattern"]="^Missing$"
        self.assertTrue(any("^Missing$ ERROR" in line for line in self.lines(cfg)))
        cfg["checks"][0]["file_pattern"]="^Absent$"
        self.assertTrue(any("^Absent$ ERROR" in line for line in self.lines(cfg)))
        cfg["checks"]=[];self.assertEqual(self.lines(cfg),["checks ERROR"])

    def test_blank_range_cell_and_embedded_newline(self):
        cfg=deepcopy(self.cfg);cfg["checks"][0]["range"]="A1:C1"
        self.snap["files"][0]["name"]="name\nextra"
        lines=self.lines(cfg)
        self.assertEqual(len(lines),1);self.assertNotIn("\n",lines[0]);self.assertTrue(lines[0].endswith(" ERROR"))

    def test_cli_summary_stdout_file_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);snap=root/"s.json";cfg=root/"c.json";out=root/"status.txt"
            config=deepcopy(self.cfg);config["files"]["folder_ids"]=["changed-next-capture"]
            write_json(snap,self.snap);write_json(cfg,config)
            args=["check",str(snap),"--config",str(cfg),"--format","summary"]
            stdout,stderr=io.StringIO(),io.StringIO()
            with redirect_stdout(stdout),redirect_stderr(stderr):
                self.assertEqual(main(args),0)
                self.assertEqual(main(args+["--output",str(out)]),0)
                self.assertEqual(main(args+["--output",str(out)]),2)
            self.assertTrue(stdout.getvalue().strip().endswith(" OK"))
            self.assertEqual(out.read_text(encoding="utf-8"),stdout.getvalue())
