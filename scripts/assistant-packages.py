#!/usr/bin/env python3
"""Write the packages that teach AI assistants to work with BioManager.

    python scripts/assistant-packages.py           # writes them
    python scripts/assistant-packages.py --check   # lists files out of date, exits 1 if any

A person adds the plugin once, in their assistant app; from then on "I
want to change something in BioManager" is enough. It carries a skill (how
to work with BioManager, in SKILL.md, which most assistant apps read), the
prompts as commands, and, in Claude Code, the connection to the lab's
own MCP address, asked for when the plugin is enabled. Elsewhere each lab
adds its own address (each lab's differs), from Help → Connect an AI
assistant.

One folder, plugins/biomanager/, with a manifest for each family of apps:

    .claude-plugin/plugin.json   Claude (chat, Cowork, Claude Code); Kimi and Qwen Code convert it
    plugin.json                  Agent Plugins 1.0: ChatGPT and Codex, VS Code (GitHub Copilot)
    .cursor-plugin/plugin.json   Cursor

and two marketplaces that list it: .claude-plugin/marketplace.json (Claude
Code, VS Code; Codex reads it too) and .agents/plugins/marketplace.json
(Codex and ChatGPT's own).

The words come from app/assistant_tools.py (INSTRUCTIONS and PROMPTS), the
same the MCP servers send, so they can't drift apart: run this after
changing them (tests/test_assistant_packages.py fails while a file is out
of date). A changed skill or command also needs a new VERSION, as apps
keep people on the version they have until it changes: the test says when,
and what CONTENT becomes. The plugin's README.md is written by hand.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.assistant_tools import INSTRUCTIONS, PROMPTS  # noqa: E402

PLUGIN = ROOT / "plugins" / "biomanager"
# The plugin's version, and a digest of the skill and commands it was set for.
VERSION = "1.1.0"
CONTENT = "1bc2a57e64d0791a"
SITE = "https://biomanager.org"
REPO = "https://github.com/gaspolymerase/biomanager"

DESCRIPTION = ("Tell your assistant what you did in the lab, in your words or with a photo of your notes; it "
               "proposes the records in your lab's BioManager, and you approve them there.")

SKILL_DESCRIPTION = (
    "Record and look up a lab's work in BioManager, the lab's database of animals (mice, zebrafish, flies, worms "
    "and other organisms), cages, litters, experiments, inventories and notebook. Use whenever the person mentions "
    "BioManager or their lab's records, or wants to log, record, update, change or look up animals, cages, "
    "litters, tanks, vials, experiments or what is due, even if they only say \"I want to change something in "
    "BioManager\". Not for working on BioManager's source code.")

# How to connect, said by the skill when the BioManager tools aren't in the
# conversation. The Connect page has each app's steps with the lab's address.
CONNECT = """\
- Every way in is on BioManager's **Help → Connect an AI assistant**, with this lab's address filled in \
(it ends in /api/v1/mcp) and one-click buttons for some apps.
- Claude (web, desktop, phone): Settings → Connectors → Add custom connector with that address; sign in with \
a connection code from the same page. Claude Code: this plugin asks for the address, then type /mcp, choose \
biomanager and press Allow in the browser.
- ChatGPT: Plugins → + → Add custom MCP server with that address (on the web; a Business, Enterprise or Edu \
workspace with developer mode). Codex: `codex mcp add biomanager --url <address>`, then \
`codex mcp login biomanager`.
- Cursor, VS Code, Cherry Studio: the buttons on the Connect page. Other apps: add the address as a \
streamable HTTP MCP server; it signs in with OAuth, or with a token from the same page.
- claude.ai and ChatGPT reach BioManager over the internet, so they need the lab's server to be on it; apps \
on the person's own computer (Claude Code, Codex, Cursor, VS Code, Cherry Studio) also reach a desktop app or \
a server on the lab network."""


def skill() -> str:
    return f"""---
name: biomanager
description: {json.dumps(SKILL_DESCRIPTION, ensure_ascii=False)}
---

# BioManager

{INSTRUCTIONS}

## When BioManager isn't connected

The tools above (lab_overview, resolve, propose_changes…) come from the lab's own BioManager. If they \
aren't available in this conversation, BioManager isn't connected yet: don't work without it, and don't \
ask for a token in the chat. Tell the person, briefly, how to connect:

{CONNECT}
"""


# Each prompt as a command: its slug, the hint for what follows it, and its
# text with that placeholder in it.
def commands(placeholder: str) -> dict[str, tuple[str, str, str]]:
    out = {}
    for name, (title, args, render) in PROMPTS.items():
        if not args:
            text, hint = render({}), ""
        elif args[0].get("required"):
            text, hint = render({args[0]["name"]: placeholder}), args[0]["description"]
        else:
            text, hint = render({}) + f"\n\n{placeholder}", args[0]["description"]
        out[name.replace("_", "-")] = (title, hint, text)
    return out


def command_file(title: str, hint: str, text: str) -> str:
    head = f"---\ndescription: {json.dumps(title, ensure_ascii=False)}\n"
    if hint:
        head += f"argument-hint: {json.dumps('[' + hint.lower() + ']', ensure_ascii=False)}\n"
    return head + "---\n\n" + text.rstrip() + "\n"


def plugin_json() -> dict:
    """Claude's manifest."""
    return {
        "name": "biomanager",
        "displayName": "BioManager",
        "version": VERSION,
        "description": DESCRIPTION,
        "author": {"name": "BioManager", "url": SITE},
        "homepage": f"{SITE}/guide/ai-assistants",
        "repository": REPO,
        "license": "MIT",
        "keywords": ["lab", "laboratory", "mouse colony", "zebrafish", "drosophila", "lab notebook",
                     "animal facility", "LIMS"],
        "icon": "./icon.svg",
        "documentationUrl": f"{SITE}/guide/ai-assistants",
        "supportUrl": f"{REPO}/issues",
        "privacyPolicyUrl": f"{REPO}/blob/master/plugins/biomanager/README.md#privacy",
        "userConfig": {
            "mcp_address": {
                "type": "string",
                "title": "BioManager's MCP address",
                "description": "From Help → Connect an AI assistant in your BioManager. It ends in /api/v1/mcp.",
                "required": True,
            },
        },
        "mcpServers": {"biomanager": {"type": "http", "url": "${user_config.mcp_address}"}},
    }


def portable_json() -> dict:
    """Agent Plugins 1.0 (agent-plugins.org), with ChatGPT's and Codex's
    listing under extensions.com.openai. No MCP server: its address is each
    lab's own, and these apps can't ask for it when the plugin is added."""
    return {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        "name": "biomanager",
        "version": VERSION,
        "description": DESCRIPTION,
        "author": {"name": "BioManager", "url": SITE},
        "homepage": f"{SITE}/guide/ai-assistants",
        "repository": REPO,
        "license": "MIT",
        "keywords": plugin_json()["keywords"],
        "extensions": {"com.openai": {"interface": {
            "displayName": "BioManager",
            "shortDescription": "Record your lab work in BioManager, for you to approve",
            "longDescription": DESCRIPTION,
            "developerName": "BioManager",
            "category": "Productivity",
            "websiteURL": SITE,
            "privacyPolicyURL": plugin_json()["privacyPolicyUrl"],
            "defaultPrompt": "I want to record what I did in the lab today in BioManager.",
        }}},
    }


def cursor_json() -> dict:
    return {key: plugin_json()[key] for key in ("name", "displayName", "version", "description", "author",
                                                "homepage", "repository", "license", "keywords")}


def marketplace_json() -> dict:
    return {
        "name": "biomanager",
        "owner": {"name": "BioManager", "url": SITE},
        "description": "BioManager, a lab's animals, stocks and notebook, for AI assistants.",
        "plugins": [{"name": "biomanager", "source": "./plugins/biomanager", "description": DESCRIPTION}],
    }


def codex_marketplace_json() -> dict:
    return {
        "name": "biomanager",
        "plugins": [{"name": "biomanager", "source": {"source": "local", "path": "./plugins/biomanager"},
                     "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                     "category": "Productivity"}],
    }


def _json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def files() -> dict[Path, str]:
    """Every generated file and what it should hold."""
    out = {
        ROOT / ".claude-plugin" / "marketplace.json": _json(marketplace_json()),
        ROOT / ".agents" / "plugins" / "marketplace.json": _json(codex_marketplace_json()),
        PLUGIN / ".claude-plugin" / "plugin.json": _json(plugin_json()),
        PLUGIN / "plugin.json": _json(portable_json()),
        PLUGIN / ".cursor-plugin" / "plugin.json": _json(cursor_json()),
        PLUGIN / "skills" / "biomanager" / "SKILL.md": skill(),
        PLUGIN / "icon.svg": (ROOT / "app" / "static" / "icon.svg").read_text(encoding="utf-8"),
    }
    for slug, (title, hint, text) in commands("$ARGUMENTS").items():
        out[PLUGIN / "commands" / f"{slug}.md"] = command_file(title, hint, text)
    return out


def content_digest() -> str:
    """What people get from the plugin: the skill and the commands."""
    parts = [text for p, text in sorted(files().items()) if p.suffix == ".md" and p.name != "README.md"]
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()[:16]


def stale() -> list[Path]:
    return [p for p, text in files().items()
            if not p.exists() or p.read_text(encoding="utf-8") != text]


def main() -> None:
    if "--check" in sys.argv:
        old = stale()
        for p in old:
            print(f"out of date: {p.relative_to(ROOT)}")
        sys.exit(1 if old else 0)
    for p, text in files().items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"wrote {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
