import unittest
from unittest.mock import Mock, patch
from cokw_lore_sheets.config import validate
from cokw_lore_sheets.model import capture
from cokw_lore_sheets.google import GoogleProvider
from cokw_lore_sheets.webapp import WebAppProvider

class RecursiveTests(unittest.TestCase):
    def provider(self):
        p=Mock(account_id="synthetic")
        p.list_folders.side_effect=lambda key: {"root":["child"],"child":["grand"],"grand":["root"]}[key]
        p.list_files.return_value=[{"id":"file","name":"Book","parents":["grand"],"ownedByMe":True},
                                  {"id":"outside","name":"Other","parents":["elsewhere"],"ownedByMe":True}]
        p.fetch.return_value=({"id":"file","name":"Book","parents":["grand"]},
                              {"spreadsheetId":"file","sheets":[]})
        return p

    def test_descendants_overlap_and_cycles(self):
        cfg=validate({"files":{"folder_ids":["root","child"],"recursive":True}})
        p=self.provider(); result=capture(p,cfg)
        self.assertTrue(result["complete"])
        self.assertEqual([f["id"] for f in result["files"]],["file"])
        self.assertEqual(p.list_folders.call_count,3)
        self.assertEqual(p.list_files.call_args.args[0]["folder_ids"],["child","grand","root"])
        self.assertEqual(result["selection"]["folder_ids"],["child","root"])
        self.assertEqual(cfg["files"]["folder_ids"],["child","root"])

    def test_nonrecursive_does_not_expand(self):
        cfg=validate({"files":{"folder_ids":["root"]}})
        p=self.provider(); self.assertEqual(capture(p,cfg)["files"],[])
        p.list_folders.assert_not_called()

    def test_no_roots_does_not_expand(self):
        p=self.provider();p.list_files.return_value=[]
        self.assertTrue(capture(p,validate({"files":{"recursive":True}}))["complete"])
        p.list_folders.assert_not_called()

    def test_folder_error_aborts_before_catalog(self):
        p=self.provider();p.list_folders.side_effect=ValueError("Folder unavailable")
        with self.assertRaisesRegex(ValueError,"unavailable"):
            capture(p,validate({"files":{"folder_ids":["root"],"recursive":True}}))
        p.list_files.assert_not_called()

    def test_recursive_requires_boolean(self):
        with self.assertRaises(ValueError): validate({"files":{"recursive":"true"}})

    def test_oauth_folder_pages(self):
        p=GoogleProvider.__new__(GoogleProvider);p.drive=Mock()
        p.drive.files().get().execute.return_value={"mimeType":"application/vnd.google-apps.folder"}
        p.drive.files().list().execute.side_effect=[{"files":[{"id":"child"}],"nextPageToken":"p2"},
                                                  {"files":[{"id":"grand"}]}]
        self.assertEqual(p.list_folders("root"),["child","grand"])

    def test_oauth_incomplete_folders_fail(self):
        p=GoogleProvider.__new__(GoogleProvider);p.drive=Mock()
        p.drive.files().get().execute.return_value={"mimeType":"application/vnd.google-apps.folder"}
        p.drive.files().list().execute.return_value={"incompleteSearch":True}
        with self.assertRaises(ValueError):p.list_folders("root")

    def test_webapp_folder_pages(self):
        p=WebAppProvider.__new__(WebAppProvider)
        p.call=Mock(side_effect=[{"folders":["child"],"nextPageToken":"p2"},{"folders":["grand"]}])
        self.assertEqual(p.list_folders("root"),["child","grand"])
        self.assertEqual(p.call.call_args.kwargs["page_token"],"p2")

    def test_webapp_repeated_folder_page_fails(self):
        p=WebAppProvider.__new__(WebAppProvider)
        p.call=Mock(return_value={"folders":[],"nextPageToken":"same"})
        with self.assertRaises(ValueError):p.list_folders("root")
