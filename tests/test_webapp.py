import io
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError
from cokw_lore_sheets.webapp import WebAppProvider
from cokw_lore_sheets.cli import parser

ENV = {"LORE_SHEETS_WEB_APP_URL":"https://script.google.com/macros/s/synthetic/exec", "LORE_SHEETS_API_KEY":"synthetic-secret"}
def response(data):
    return io.BytesIO(json.dumps(data).encode())

class WebAppTests(unittest.TestCase):
    def test_default_transport(self):
        self.assertEqual(parser().parse_args(["dump","--config","example.json"]).transport,"webapp")

    @patch.dict("os.environ", ENV, clear=True)
    @patch("cokw_lore_sheets.webapp.urlopen")
    def test_secret_body_and_account(self, opening):
        opening.return_value=response({"ok":True,"data":{"account_id":"account"}})
        provider=WebAppProvider()
        request=opening.call_args.args[0]
        self.assertEqual(provider.account_id,"account")
        self.assertNotIn("synthetic-secret",request.full_url)
        self.assertEqual(json.loads(request.data)["api_key"],"synthetic-secret")

    @patch.dict("os.environ", ENV, clear=True)
    @patch("cokw_lore_sheets.webapp.urlopen")
    def test_unauthorized(self, opening):
        opening.return_value=response({"ok":False,"error":"UNAUTHORIZED"})
        with self.assertRaisesRegex(ValueError,"UNAUTHORIZED"): WebAppProvider()

    @patch.dict("os.environ", ENV, clear=True)
    @patch("cokw_lore_sheets.webapp.urlopen")
    def test_html_login(self, opening):
        opening.return_value=io.BytesIO(b"<html>Login</html>")
        with self.assertRaisesRegex(ValueError,"deployment"): WebAppProvider()

    @patch.dict("os.environ", ENV, clear=True)
    @patch("cokw_lore_sheets.webapp.urlopen")
    def test_network_error_redacted(self, opening):
        opening.side_effect=URLError("synthetic-secret")
        with self.assertRaises(ValueError) as caught: WebAppProvider()
        self.assertNotIn("synthetic-secret",str(caught.exception))

    @patch.dict("os.environ", ENV, clear=True)
    @patch("cokw_lore_sheets.webapp.urlopen")
    def test_pagination_and_fetch(self, opening):
        opening.side_effect=[response({"ok":True,"data":data}) for data in [
            {"account_id":"account"}, {"files":[{"id":"one"}],"nextPageToken":"p2"},
            {"files":[{"id":"two"}]}, {"metadata":{"id":"one"},"spreadsheet":{"sheets":[]}}]]
        provider=WebAppProvider()
        self.assertEqual(len(provider.list_files({})),2)
        self.assertEqual(provider.fetch({"id":"one"},{"include_results":True,"max_cells_per_sheet":100}),
                         ({"id":"one"},{"sheets":[]}))

    @patch.dict("os.environ", {}, clear=True)
    def test_configuration_missing(self):
        with self.assertRaisesRegex(ValueError,"LORE_SHEETS_WEB_APP_URL"): WebAppProvider()

    @patch.dict("os.environ", ENV, clear=True)
    def test_arbitrary_host_rejected(self):
        with self.assertRaises(ValueError): WebAppProvider("https://example.com/exec")
