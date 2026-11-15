"""Synthetic offline adapter for examples and tests."""
from .storage import load_json


class FixtureProvider:
    def __init__(self, path):
        self.fixture = load_json(path)
        self.account_id = "fixture:" + self.fixture["account"]

    def list_files(self, selection):
        return [item["metadata"] for item in self.fixture["files"]]

    def fetch(self, file, config):
        item = next(item for item in self.fixture["files"] if item["metadata"]["id"] == file["id"])
        if item.get("error"):
            raise ValueError("Synthetic read failure")
        return item["metadata"], item["spreadsheet"]
