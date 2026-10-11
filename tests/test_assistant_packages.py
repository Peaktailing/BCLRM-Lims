"""The packages for AI assistants (scripts/assistant-packages.py): the Claude
plugin and the others, made from app/assistant_tools.py's own words."""
from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("assistant_packages", ROOT / "scripts" / "assistant-packages.py")
packages = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(packages)


class AssistantPackages(unittest.TestCase):
    def test_every_generated_file_is_current(self):
        self.assertEqual([str(p.relative_to(ROOT)) for p in packages.stale()], [],
                         "run python scripts/assistant-packages.py")

    def test_a_changed_skill_has_a_new_version(self):
        self.assertEqual(packages.content_digest(), packages.CONTENT,
                         "the skill or a command changed: raise VERSION in scripts/assistant-packages.py and set "
                         f"CONTENT = \"{packages.content_digest()}\"")

    def test_every_manifest_names_the_same_plugin(self):
        for manifest in (".claude-plugin/plugin.json", "plugin.json", ".cursor-plugin/plugin.json"):
            data = json.loads((packages.PLUGIN / manifest).read_text(encoding="utf-8"))
            self.assertEqual((data["name"], data["version"]), ("biomanager", packages.VERSION), manifest)

    def test_the_chatgpt_listing_keeps_within_its_limits(self):
        listing = json.loads((packages.PLUGIN / "plugin.json").read_text(encoding="utf-8"))
        ui = listing["extensions"]["com.openai"]["interface"]
        self.assertLessEqual(len(ui["displayName"]), 30)
        self.assertLessEqual(len(ui["shortDescription"]), 30)
        self.assertLessEqual(len(ui["longDescription"]), 4000)
        self.assertLessEqual(len(ui["defaultPrompt"]), 128)
        self.assertIn(ui["category"], ("Productivity", "Creativity", "Developer Tools", "Business & Operations",
                                       "Data & Analytics", "Communication", "Education & Research", "Security",
                                       "Finance", "Healthcare", "Travel", "Entertainment", "Other"))
        self.assertNotIn("mcpServers", listing)                         # skills only: each lab adds its own server
        for key in ("logo", "composerIcon"):
            svg = (packages.PLUGIN / ui[key]).read_text(encoding="utf-8")
            box = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
            self.assertTrue(box and box.group(1) == box.group(2) and int(box.group(1)) >= 48, key)
        for name in packages.OPENAI_FILES:
            self.assertTrue((packages.PLUGIN / name).is_file(), name)

    def test_the_skill_carries_the_instructions_and_says_how_to_connect(self):
        text = (packages.PLUGIN / "skills" / "biomanager" / "SKILL.md").read_text(encoding="utf-8")
        front = re.match(r"---\nname: biomanager\ndescription: (.+)\n---\n", text)
        self.assertIsNotNone(front)
        self.assertLessEqual(len(json.loads(front.group(1))), 1024)
        self.assertIn(packages.INSTRUCTIONS, text)
        self.assertIn("I want to change something in BioManager", text)
        self.assertIn("Help → Connect an AI assistant", text)

    def test_the_plugin_asks_for_the_address_and_holds_no_secret(self):
        manifest = json.loads((packages.PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["mcpServers"]["biomanager"]["url"], "${user_config.mcp_address}")
        self.assertIn("mcp_address", manifest["userConfig"])
        for path in packages.PLUGIN.rglob("*"):
            if path.is_file():
                self.assertNotIn("bmt_", path.read_text(encoding="utf-8"), path)
                self.assertLess(path.stat().st_size, 256 * 1024, path)
        self.assertGreaterEqual(len((packages.PLUGIN / "README.md").read_text(encoding="utf-8").split()), 40)

    def test_each_prompt_is_a_command(self):
        for name in packages.PROMPTS:
            text = (packages.PLUGIN / "commands" / f"{name.replace('_', '-')}.md").read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\ndescription: "), name)


if __name__ == "__main__":
    unittest.main()
