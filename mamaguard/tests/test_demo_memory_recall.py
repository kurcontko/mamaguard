"""Unit tests for the memory-recall demo script (scripts/demo_memory_recall.py)."""

import base64
import importlib.util
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path


def _load_demo_module():
    """Load scripts/demo_memory_recall.py as a module without side effects."""
    repo_root = Path(__file__).resolve().parents[2]
    path = repo_root / "scripts" / "demo_memory_recall.py"
    spec = importlib.util.spec_from_file_location("demo_memory_recall", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestBuildMemoryDoc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_demo_module()

    def test_schema_matches_inject_memory_block_query(self):
        """The doc MUST match the category/type/subject fields that
        mamaguard.shared.memory.inject_memory_block queries against."""
        doc = self.mod._build_memory_doc(
            "p-1", "test note content", datetime.now(UTC),
        )
        self.assertEqual(doc["resourceType"], "DocumentReference")
        self.assertEqual(doc["status"], "current")
        self.assertEqual(doc["subject"]["reference"], "Patient/p-1")
        # Category is the search key -- must be stable
        cats = doc["category"][0]["coding"][0]
        self.assertEqual(cats["system"], self.mod.MEMORY_SYSTEM)
        self.assertEqual(cats["code"], self.mod.MEMORY_CATEGORY_CODE)
        # Type carries the agent-memory-note marker + subtype
        type_codes = [c["code"] for c in doc["type"]["coding"]]
        self.assertIn(self.mod.MEMORY_TYPE_CODE, type_codes)
        # Author is display-only (HAPI referential integrity)
        author = doc["author"][0]
        self.assertIn("display", author)
        self.assertNotIn("reference", author)
        # Demo tag present so --cleanup can find this doc
        tag_codes = [t["code"] for t in doc["meta"]["tag"]]
        self.assertIn(self.mod.SEED_TAG, tag_codes)

    def test_content_is_base64_markdown(self):
        note = "## Visit 2026-03-10\n\nDr. Kim declined metformin."
        doc = self.mod._build_memory_doc("p-1", note, datetime.now(UTC))
        att = doc["content"][0]["attachment"]
        self.assertEqual(att["contentType"], "text/markdown")
        decoded = base64.b64decode(att["data"]).decode("utf-8")
        self.assertEqual(decoded, note)

    def test_seed_note_mentions_metformin_decline(self):
        """The canned demo note must contain the keywords that drive the
        recall demo -- if these shift, the demo video talking points break."""
        note = self.mod.SEED_NOTE_MARKDOWN.lower()
        for keyword in ("metformin", "dr. kim", "french", "housing"):
            self.assertIn(keyword, note, f"demo note missing keyword: {keyword}")


if __name__ == "__main__":
    unittest.main()
