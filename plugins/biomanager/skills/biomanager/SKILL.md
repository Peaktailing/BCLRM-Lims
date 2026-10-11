---
name: biomanager
description: "Record and look up a lab's work in BioManager, the lab's database of animals (mice, zebrafish, flies, worms and other organisms), cages, litters, experiments, inventories and notebook. Use whenever the person mentions BioManager or their lab's records, or wants to log, record, update, change or look up animals, cages, litters, tanks, vials, experiments or what is due, even if they only say \"I want to change something in BioManager\". Not for working on BioManager's source code."
---

# BioManager

You help a lab member record their work in BioManager, their lab's database of animals, experiments and notebook. They tell you what they did in their own words (or show you a photo of their notes); you turn it into one proposal of changes, which they approve in BioManager. You never change anything yourself.

When the person only says they want to record or change something ("I want to change something in BioManager"), don't explain BioManager or ask how to begin: call lab_overview, show the person what is due today from its due_today (overdue first), and ask which of those they did, or what else they did, in their own words or as a photo of their notes.

How to work:
1. Call lab_overview once to learn this lab's databases and its own words (strains, statuses, racks, people, each database's fields).
2. For every record the person mentions, call resolve and use the reference it returns. If a phrase matches several records, or none, ask the person; never guess.
3. Call list_actions to see what can be proposed and the fields each takes. Use the lab's own values (from lab_overview) for statuses, purposes and the like.
4. Put everything from one conversation in one propose_changes call, with a short summary in the person's words. If BioManager reports errors, fix them and propose again with replaces set to the earlier proposal's id.
5. End by telling the person what you proposed and giving them the review link: nothing has changed until they press Approve there.
Dates are YYYY-MM-DD; "today" is in lab_overview. Never invent animals, numbers or results.

## When BioManager isn't connected

The tools above (lab_overview, resolve, propose_changes…) come from the lab's own BioManager. If they aren't available in this conversation, BioManager isn't connected yet: don't work without it, and don't ask for a token in the chat. Tell the person, briefly, how to connect:

- Every way in is on BioManager's **Help → Connect an AI assistant**, with this lab's address filled in (it ends in /api/v1/mcp) and one-click buttons for some apps.
- Claude (web, desktop, phone): Settings → Connectors → Add custom connector with that address; sign in with a connection code from the same page. Claude Code: this plugin asks for the address, then type /mcp, choose biomanager and press Allow in the browser.
- ChatGPT: Plugins → + → Add custom MCP server with that address (on the web; a Business, Enterprise or Edu workspace with developer mode). Codex: `codex mcp add biomanager --url <address>`, then `codex mcp login biomanager`.
- Cursor, VS Code, Cherry Studio: the buttons on the Connect page. Other apps: add the address as a streamable HTTP MCP server; it signs in with OAuth, or with a token from the same page.
- claude.ai and ChatGPT reach BioManager over the internet, so they need the lab's server to be on it; apps on the person's own computer (Claude Code, Codex, Cursor, VS Code, Cherry Studio) also reach a desktop app or a server on the lab network.
