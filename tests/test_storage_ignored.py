import subprocess
import tempfile
import unittest
from pathlib import Path
from cokw_lore_sheets.storage import write_json, private_path

class IgnoredOutputTests(unittest.TestCase):
    def test_only_untracked_ignored_output_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            subprocess.run(["git","init",str(root)],check=True,capture_output=True)
            (root/".gitignore").write_text("tmp/\n",encoding="utf-8")
            write_json(root/"tmp"/"capture.json",{"complete":True})
            self.assertTrue((root/"tmp"/"capture.json").is_file())
            with self.assertRaises(ValueError): private_path(root/"tmp"/"token.json")
            with self.assertRaises(ValueError): write_json(root/"capture.json",{})
            subprocess.run(["git","-C",str(root),"add","-f","tmp/capture.json"],check=True,capture_output=True)
            with self.assertRaises(ValueError): write_json(root/"tmp"/"capture.json",{})
