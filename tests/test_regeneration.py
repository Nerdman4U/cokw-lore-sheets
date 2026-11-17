import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from cokw_lore_sheets.regeneration import RegenerationService
from cokw_lore_sheets.cli import main, parser


class RegenerationTests(unittest.TestCase):
    def test_exact_simple_command(self):
        args = parser().parse_args(["regenerate", "file", "TMP_Example"])
        self.assertEqual((args.file_id, args.sheet_name, args.dry_run), ("file", "TMP_Example", False))
        self.assertIsNone(parser().parse_args(["regenerate", "file"]).sheet_name)

    def test_read_precedes_write_and_pins_schema_revision(self):
        provider = Mock()
        provider.call.side_effect = [{"schema_revision": "revision"}, {"status": "regenerated"}]
        self.assertEqual(RegenerationService(provider).regenerate("file", "TMP_Example")["status"], "regenerated")
        self.assertEqual(provider.call.call_args_list[0].args, ("regenerationSchema",))
        self.assertEqual(provider.call.call_args_list[1].kwargs, {"file_id": "file", "sheet_name": "TMP_Example", "schema_revision": "revision"})

    def test_dry_run_never_writes(self):
        provider = Mock()
        provider.call.return_value = {"schema_revision": "revision"}
        self.assertEqual(RegenerationService(provider).regenerate("file", dry_run=True)["status"], "planned")
        self.assertEqual(provider.call.call_count, 1)

    def test_preflight_failure_never_sends_write(self):
        provider = Mock()
        provider.call.side_effect = ValueError("DUPLICATE_ROW_KEY")
        with self.assertRaisesRegex(ValueError, "DUPLICATE_ROW_KEY"):
            RegenerationService(provider).regenerate("file")
        self.assertEqual(provider.call.call_count, 1)

    def test_invalid_targets_never_call_transport(self):
        provider = Mock()
        for file, sheet in [("../file", None), ("file", "Source"), ("file", "TMP_BACKUP_example")]:
            with self.assertRaises(ValueError):
                RegenerationService(provider).regenerate(file, sheet)
        provider.call.assert_not_called()

    @patch("cokw_lore_sheets.regeneration.regenerate")
    def test_cli_works_without_audit_config_and_reports_pending(self, regenerate):
        regenerate.return_value = {"status": "pending", "backup_sheet": "TMP_BACKUP_example"}
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["regenerate", "file"]), 1)
        self.assertEqual(json.loads(output.getvalue())["backup_sheet"], "TMP_BACKUP_example")

    @patch("cokw_lore_sheets.regeneration.regenerate")
    def test_completed_cli_exit(self, regenerate):
        regenerate.return_value = {"status": "regenerated"}
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["regenerate", "file", "TMP_Example"]), 0)


if __name__ == "__main__":
    unittest.main()
