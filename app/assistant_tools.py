"""What an AI assistant can do with BioManager, whichever way it connects.

The local MCP server (mcp/biomanager_mcp.py, stdio, run on the person's
computer) and the server's own MCP endpoint (app/mcp_http.py, /api/v1/mcp,
for claude.ai, Claude's apps and ChatGPT) offer the same tools, described
here once: the instructions, each tool's description and input schema, the
prompts, and the tool functions over an `Api`, which is BioManager's
/api/v1 with the person's token (over HTTP, or in-process on the server).
Standard library only: the local server imports this without the app's
dependencies.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

INSTRUCTIONS = """\
You help a lab member record their work in BioManager, their lab's database of animals, \
experiments and notebook. They tell you what they did in their own words (or show you a photo \
of their notes); you turn it into one proposal of changes, which they approve in BioManager. \
You never change anything yourself.

When the person only says they want to record or change something ("I want to change something in \
BioManager"), don't explain BioManager or ask how to begin: call lab_overview, show the person what is due \
today from its due_today (overdue first), and ask which of those they did, or what else they did, in their \
own words or as a photo of their notes.

How to work:
1. Call lab_overview once to learn this lab's databases and its own words (strains, statuses, \
racks, people, each database's fields).
2. For every record the person mentions, call resolve and use the reference it returns. If a \
phrase matches several records, or none, ask the person; never guess.
3. Call list_actions to see what can be proposed and the fields each takes. Use the lab's own \
values (from lab_overview) for statuses, purposes and the like.
4. Put everything from one conversation in one propose_changes call, with a short summary in the \
person's words. If BioManager reports errors, fix them and propose again with replaces set to the \
earlier proposal's id.
5. End by telling the person what you proposed and giving them the review link: nothing has \
changed until they press Approve there.
Dates are YYYY-MM-DD; "today" is in lab_overview. Never invent animals, numbers or results.

BioManager computes; you talk. Never work out a number yourself that a BioManager tool can: how many \
animals fit (availability), breeding odds and matings (breeding_plan), group allocation (randomize), \
animals per group (power_analysis), when stock runs out (reorder_forecast), the week's checks \
(lab_checks), an experiment's facts (experiment_summary). Call the tool, give its numbers with the \
assumptions it states, and say so when it can't answer rather than estimating."""


class ApiError(Exception):
    pass


class Api:
    """BioManager's /api/v1, with a token."""

    def __init__(self, base: str, token: str, timeout: float = 60):
        self.base = base.rstrip("/")
        self.token = token
        self.timeout = timeout

    def request(self, method: str, path: str, query: dict | None = None, body: dict | None = None):
        url = f"{self.base}/api/v1/{path.lstrip('/')}"
        if query:
            url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v not in (None, "")})
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/json",
            **({"Content-Type": "application/json"} if data is not None else {})})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode() or "null")
        except urllib.error.HTTPError as e:
            try:
                message = json.loads(e.read().decode()).get("error")
            except (ValueError, AttributeError):
                message = None
            raise ApiError(message or f"BioManager answered {e.code}.") from None
        except urllib.error.URLError as e:
            raise ApiError(f"Can't reach BioManager at {self.base}: {e.reason}. Is it running, and is "
                           "BIOMANAGER_URL right?") from None


# ---------------------------------------------------------------- the tools, as plain functions

# What `get` and `list_records` may read: the API's own read paths.
READABLE = ("mice", "cages", "litters", "strains", "tanks", "fish", "plasmids", "stocks", "inventories",
            "experiments", "proposals", "me", "regimens")


def _readable(path: str) -> str:
    path = (path or "").strip().strip("/")
    if path.startswith("api/v1/"):
        path = path[len("api/v1/"):]
    if ".." in path or not path or path.split("/")[0] not in READABLE:
        raise ApiError(f"Read one of: {', '.join(READABLE)} (e.g. mice/1043, cages, experiments/12).")
    return path


# How many of today's jobs lab_overview shows; whats_due has the rest.
DUE_TODAY = 15


def lab_overview(api: Api) -> dict:
    """Who the assistant acts for, the lab's own words, what is due today,
    and how to work: in a tool result, which every app hands to its model,
    as not every app passes on the server's instructions."""
    me = api.request("GET", "me")
    try:
        due = [i for i in whats_due(api, 0) if i.get("status") in ("overdue", "today")]
    except ApiError:
        due = []
    return {"you": me, "lab": api.request("GET", "vocabulary"), "due_today": due[:DUE_TODAY],
            "due_today_more": max(0, len(due) - DUE_TODAY), "how_to_work": INSTRUCTIONS}


def resolve(api: Api, q: str, kinds: str = "") -> list:
    return api.request("GET", "resolve", {"q": q, "kinds": kinds})["data"]


def get(api: Api, path: str):
    return api.request("GET", _readable(path))


def list_records(api: Api, path: str, filters: dict | None = None, limit: int = 100) -> dict:
    return api.request("GET", _readable(path), {**(filters or {}), "limit": limit})


def whats_due(api: Api, days: int = 7) -> list:
    return api.request("GET", "due", {"days": days})["data"]


def list_actions(api: Api) -> list:
    return api.request("GET", "actions")["data"]


def propose_changes(api: Api, summary: str, changes: list, replaces: int | None = None,
                    source: str | None = None) -> dict:
    body = {"summary": summary, "changes": changes,
            "source": source or os.environ.get("BIOMANAGER_ASSISTANT") or "AI assistant"}
    if replaces is not None:
        body["replaces"] = replaces
    out = api.request("POST", "proposals", body=body)
    out["next"] = ("Nothing has changed yet. Give the person the review_url: they approve or discard it there."
                   if out.get("status") == "pending" else
                   "BioManager can't apply this as it is: fix the errors and propose again, with replaces set "
                   "to this id.")
    return out


def proposal_status(api: Api, proposal_id: int) -> dict:
    return api.request("GET", f"proposals/{int(proposal_id)}")


def discard_proposal(api: Api, proposal_id: int) -> dict:
    return api.request("POST", f"proposals/{int(proposal_id)}/discard", body={})


def describe_actions(actions: list) -> str:
    """The catalogue, briefly, for propose_changes' description."""
    lines = []
    for a in actions:
        fields = ", ".join(f"{name}{'*' if name in a['fields'].get('required', []) else ''}"
                           for name in a["fields"].get("properties", {}))
        target = f" target: {a['target']};" if a.get("target") else ""
        lines.append(f"- {a['name']} ({a['area']}):{target} fields: {fields or '-'}. {a['help']}")
    return "\n".join(lines)


PROPOSE_HELP = """\
Send changes to BioManager as one proposal for the person to approve. Nothing changes until they \
press Approve in BioManager. changes is a list of {"action", "target", "fields"}: target is a \
reference from resolve ({"kind": "cage", "id": 412}) or what the lab writes on the record (cage \
88, mouse 1043, FV12); fields as below (* required; list_actions has each field's details). The \
reply has each change's summary, warnings and errors, and the review_url to give the person."""


# ---------------------------------------------------------------- tools and prompts, described once

def _obj(properties: dict, required: tuple = ()) -> dict:
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


TOOLS = {
    "lab_overview": (
        "Start here whenever the person mentions BioManager, their lab, colony, mice, cages, litters, fish, tanks, "
        "vials, plates, experiments or notebook, or wants to record, log, update, change or look up anything there, "
        "even if they only say \"I want to change something in BioManager\". Returns how to work with BioManager, "
        "this lab's databases and its own words (strains, statuses, purposes, racks, people, each database's "
        "fields), today's date, what is due today, and who you are acting for.",
        _obj({}), lambda api, a: lab_overview(api)),
    "resolve": (
        "Find the records a phrase means (\"cage 88\", \"#1043\", \"FV12\", a line or experiment's name), each with "
        "the reference to use in a proposal. kinds narrows it (comma-separated: cage, mouse, litter, tank, "
        "stock_unit, experiment, notebook_page…). Several matches: ask the person which.",
        _obj({"q": {"type": "string", "description": "What the person called it"},
              "kinds": {"type": "string", "description": "Only these kinds, comma-separated"}}, ("q",)),
        lambda api, a: {"matches": resolve(api, a["q"], a.get("kinds", ""))}),
    "get": (
        "Read one record or list from BioManager's API, e.g. mice/1043, cages/88, experiments/12 (with its steps, "
        "animals and readouts), stocks.",
        _obj({"path": {"type": "string", "description": "e.g. mice/1043"}}, ("path",)),
        lambda api, a: get(api, a["path"])),
    "list": (
        "List records with filters, e.g. path=mice, filters={\"alive\": \"true\", \"cage\": \"88\"}; path=experiments, "
        "filters={\"status\": \"active\"}.",
        _obj({"path": {"type": "string"}, "filters": {"type": "object", "description": "Query filters"},
              "limit": {"type": "integer", "description": "At most this many (default 100)"}}, ("path",)),
        lambda api, a: list_records(api, a["path"], a.get("filters"), a.get("limit", 100))),
    "whats_due": (
        "What is due, as BioManager's Home lists it (weanings, genotyping, flips, scheduled jobs, experiment steps), "
        "overdue first, up to `days` ahead. Each item may carry `propose`: the change that records it done.",
        _obj({"days": {"type": "integer", "description": "How many days ahead (default 7)"}}),
        lambda api, a: {"due": whats_due(api, a.get("days", 7))}),
    "list_actions": (
        "Every action a proposal may contain, with its target and fields (JSON Schema).",
        _obj({}), lambda api, a: {"actions": list_actions(api)}),
    "propose_changes": (
        None,  # PROPOSE_HELP and the lab's own actions: propose_description()
        _obj({"summary": {"type": "string", "description": "What this proposal records, in the person's words"},
              "changes": {"type": "array", "items": {"type": "object"},
                          "description": "Each {action, target, fields}"},
              "replaces": {"type": "integer", "description": "The id of an earlier proposal this corrects"}},
             ("summary", "changes")),
        lambda api, a: propose_changes(api, a["summary"], a["changes"], a.get("replaces"), a.get("_source"))),
    "proposal_status": (
        "A proposal's status (pending, approved, discarded, superseded, expired, invalid) and each change as "
        "BioManager previewed it.",
        _obj({"proposal_id": {"type": "integer"}}, ("proposal_id",)),
        lambda api, a: proposal_status(api, a["proposal_id"])),
    "discard_proposal": (
        "Withdraw a proposal that is still waiting (the person asked, or you sent a wrong one).",
        _obj({"proposal_id": {"type": "integer"}}, ("proposal_id",)),
        lambda api, a: discard_proposal(api, a["proposal_id"])),
}


# ---------------------------------------------------------------- looking up and working out
#
# BioManager computes; the model talks. Each of these reads, or works
# something out from the lab's records (app/assistant_compute.py), and
# changes nothing.

def _record(a: dict) -> dict:
    """A record as asked for: ref ({"kind", "id"}), or kind and code."""
    ref = a.get("ref") or {}
    if ref:
        return {"kind": ref.get("kind"), "id": ref.get("id")}
    if not a.get("kind") or a.get("code") in (None, ""):
        raise ValueError("give ref (from resolve or search), or kind and code (kind mouse, code 1043)")
    return {"kind": a["kind"], "code": a["code"]}


def search(api: Api, q: str, limit: int = 5) -> list:
    return api.request("GET", "search", {"q": q, "limit": limit})["data"]


def history(api: Api, record: dict, limit: int = 50) -> dict:
    return api.request("GET", "history", {**record, "limit": limit})


def lineage(api: Api, record: dict) -> dict:
    return api.request("GET", "lineage", record)


def _flag(value) -> str | None:
    return None if value is None else ("true" if value else "false")


def availability(api: Api, a: dict) -> dict:
    query = {k: a.get(k) for k in ("species", "genotype", "sex", "age_min_days", "age_max_days", "on", "limit")}
    query.update(include_in_experiments=_flag(a.get("include_in_experiments")),
                 include_breeders=_flag(a.get("include_breeders")))
    return api.request("GET", "availability", query)


def breeding_plan(api: Api, a: dict) -> dict:
    return api.request("POST", "breeding-plan", body=a)


def randomize(api: Api, a: dict) -> dict:
    return api.request("POST", "randomize", body=a)


def power_analysis(api: Api, a: dict) -> dict:
    return api.request("POST", "power", body=a)


def reorder_forecast(api: Api, days: int = 30, lead_days: int = 14) -> dict:
    return api.request("GET", "reorder-forecast", {"days": days, "lead_days": lead_days})


def lab_checks(api: Api, a: dict) -> dict:
    return api.request("GET", "lab-checks", {k: a.get(k) for k in (
        "scope", "weight_loss_pct", "breeder_weeks", "unsigned_days", "expiring_days")})


def experiment_summary(api: Api, experiment_id: int) -> dict:
    return api.request("GET", f"experiments/{int(experiment_id)}/summary")


_REF = {"type": "object", "description": "The record's reference, {\"kind\", \"id\"}, from resolve or search"}
_KIND = {"type": "string", "description": "Instead of ref: what it is (mouse, cage, plasmid, stock_unit…)"}
_CODE = {"type": "string", "description": "With kind: what the lab writes on it (1043, 88, FV12)"}
_LOCI = {"type": "object", "description": "Each locus as the lab writes it in genotypes (lab_overview's "
                                          "transgenes_in_use: Cre, Foxp3…) → wt, het, hom or carrier"}

TOOLS.update({
    "search": (
        "Search BioManager as its search box does: records in every database the person can open, and the notebook "
        "pages they may read, by words in names, genotypes, notes and page text. Each match has its kind, ref (for "
        "get, history and proposals), title, a snippet and its link. To pin down a record the person names "
        "(cage 88, #1043), use resolve instead.",
        _obj({"q": {"type": "string", "description": "The words to look for"},
              "limit": {"type": "integer", "description": "At most this many of each kind (default 5)"}}, ("q",)),
        lambda api, a: {"matches": search(api, a["q"], a.get("limit", 5))}),
    "history": (
        "A record's change history, newest first: who changed what and when (field: before → after). An admin "
        "sees everyone's changes; anyone else only their own (the full history is for admins).",
        _obj({"ref": _REF, "kind": _KIND, "code": _CODE,
              "limit": {"type": "integer", "description": "At most this many (default 50)"}}),
        lambda api, a: history(api, _record(a), a.get("limit", 50))),
    "lineage": (
        "Family: a plasmid's parents and what was made from it (the tree both ways), or a mouse's parents and "
        "grandparents, its litter and littermates, and the litters it had.",
        _obj({"ref": _REF, "kind": {"type": "string", "enum": ["mouse", "plasmid"],
                                    "description": "Instead of ref: mouse or plasmid"}, "code": _CODE}),
        lambda api, a: lineage(api, _record(a))),
    "availability": (
        "How many living animals fit, and which, as BioManager counts them: genotype (words that must all be in "
        "it, ';'-separated), sex, and an age window in days on a day (default today). Mice in an active or paused "
        "experiment, and in Breeder or Breeding cages, are left out unless asked. Use its numbers; don't count.",
        _obj({"species": {"type": "string", "enum": ["mouse", "zebrafish"], "description": "Default mouse"},
              "genotype": {"type": "string", "description": "e.g. Cre; Ai14"},
              "sex": {"type": "string", "enum": ["F", "M"]},
              "age_min_days": {"type": "integer"}, "age_max_days": {"type": "integer"},
              "on": {"type": "string", "description": "The day, YYYY-MM-DD (default today)"},
              "include_in_experiments": {"type": "boolean"}, "include_breeders": {"type": "boolean"},
              "limit": {"type": "integer", "description": "List at most this many (default 200)"}}),
        lambda api, a: availability(api, a)),
    "breeding_plan": (
        "Plan breeding for a genotype, worked out by BioManager: Mendelian odds for each mating type among the "
        "lab's own breeders (or the crosses given), the lab's own litter size, weaning at P21, and how many matings "
        "to set up by which date for `count` mice of that genotype and sex, aged within the window on `by`. Tell "
        "the person the assumptions it lists, and which breeders it was unsure how to read.",
        _obj({"want": _LOCI, "sex": {"type": "string", "enum": ["F", "M"]},
              "count": {"type": "integer", "description": "How many mice are wanted"},
              "age_min_days": {"type": "integer"}, "age_max_days": {"type": "integer"},
              "by": {"type": "string", "description": "When they are needed, YYYY-MM-DD"},
              "crosses": {"type": "array", "items": {"type": "object"},
                          "description": "Instead of the lab's breeders: [{female: {locus: state}, male: {…}}]"},
              "confidence": {"type": "number", "description": "How sure to be of having enough (default 0.9)"}},
             ("want",)),
        lambda api, a: breeding_plan(api, a)),
    "randomize": (
        "Allocate mice to named groups, balanced by sex, litter (or cage) and weight, from a seed that gives the "
        "same allocation again; returns the groups, the seed and a balance table. Changes nothing: with experiment "
        "it also returns the experiment_add_animals changes to propose.",
        _obj({"animals": {"type": "array", "items": {}, "description": "The mice: numbers or references"},
              "groups": {"type": "array", "items": {},
                         "description": "Group names, or {name, size} for each when the sizes differ"},
              "seed": {"type": "integer", "description": "To repeat an allocation; left out, BioManager picks one"},
              "by": {"type": "string", "enum": ["litter", "cage"], "description": "Balance across (default litter)"},
              "experiment": {"type": "integer", "description": "The experiment's id, for the changes to propose"}},
             ("animals", "groups")),
        lambda api, a: randomize(api, a)),
    "power_analysis": (
        "Animals per group, computed exactly by BioManager: two groups (t-test) or more (one-way ANOVA), from the "
        "smallest difference worth detecting and the SD (or each group's expected mean, or Cohen's d), alpha, "
        "power and the share expected to be lost. With experiment (and day), the SD is that experiment's own "
        "readouts'. Never work out a sample size yourself.",
        _obj({"groups": {"type": "integer", "description": "How many groups (default 2)"},
              "difference": {"type": "number", "description": "The smallest difference worth detecting, in the "
                                                              "readout's units"},
              "sd": {"type": "number"}, "means": {"type": "array", "items": {"type": "number"}},
              "d": {"type": "number", "description": "Cohen's d, instead of difference and sd"},
              "alpha": {"type": "number", "description": "Default 0.05"},
              "power": {"type": "number", "description": "Default 0.8"},
              "attrition": {"type": "number", "description": "Share lost before the end, e.g. 0.1"},
              "experiment": {"type": "integer", "description": "A past experiment whose readouts give the SD"},
              "day": {"type": "string", "description": "Its day number or date (default: the day with most readings)"}}),
        lambda api, a: power_analysis(api, a)),
    "reorder_forecast": (
        "Inventory kept as a number that runs out within `days`: how much is used a week (from the changes to its "
        "quantity), days left, when it runs out and the date to reorder by, given how long an order takes.",
        _obj({"days": {"type": "integer", "description": "Running out within this many days (default 30)"},
              "lead_days": {"type": "integer", "description": "Days an order takes to arrive (default 14)"}}),
        lambda api, a: reorder_forecast(api, a.get("days", 30), a.get("lead_days", 14))),
    "lab_checks": (
        "The weekly review's checks, done by BioManager: overdue jobs, mice down 15% or more from their peak weight "
        "in an active experiment, empty cages still set up, breeders 30 weeks or older, your notebook pages unsigned "
        "for 14 days (once you sign pages), reagents expired, expiring or low, and your proposals waiting. Each check "
        "has a severity, a count and items with links; an item's propose is the change that fixes it, where one "
        "exists. scope mine: only your own records.",
        _obj({"scope": {"type": "string", "enum": ["lab", "mine"]},
              "weight_loss_pct": {"type": "number"}, "breeder_weeks": {"type": "integer"},
              "unsigned_days": {"type": "integer"}, "expiring_days": {"type": "integer"}}),
        lambda api, a: lab_checks(api, a)),
    "experiment_summary": (
        "What the records say about an experiment, for its methods: the animals (species, genotypes, sex, age and "
        "weight at the start, n per group), procedures (agent, dose, route, days, lots used), the readout, the tests "
        "used and the last day's comparison, dates; and arrive, the ARRIVE 2.0 Essential 10, each with what is "
        "recorded and what is missing. Never fill in what is missing yourself.",
        _obj({"experiment_id": {"type": "integer", "description": "The experiment's id (resolve finds it by name)"}},
             ("experiment_id",)),
        lambda api, a: experiment_summary(api, a["experiment_id"])),
})


def propose_description(api: Api) -> str:
    try:
        catalogue = describe_actions(list_actions(api))
    except ApiError as e:
        catalogue = f"(The list of actions couldn't be read now: {e} Call list_actions.)"
    return f"{PROPOSE_HELP}\n\nActions:\n{catalogue}"


def description(api: Api, name: str) -> str:
    return TOOLS[name][0] or propose_description(api)


def call_tool(api: Api, name: str, arguments: dict | None) -> dict:
    """Run a tool; what it returns, or {"error": …} in words for the assistant."""
    if name not in TOOLS:
        raise KeyError(name)
    args = dict(arguments or {})
    try:
        return TOOLS[name][2](api, args)
    except ApiError as e:
        return {"error": str(e)}
    except (KeyError, TypeError, ValueError) as e:
        return {"error": f"Check the arguments: {e}"}


PROMPTS = {
    "log_today": (
        "Log today's work from my notes",
        [{"name": "notes", "description": "What you did today", "required": True}],
        lambda a: ("Here is what I did today. Record it in BioManager: resolve every animal, cage and experiment I "
                   "mention, ask me about anything unclear, then send it all as one proposal and give me the link "
                   "to approve it. Add a short line to today's daily log too.\n\n" + a.get("notes", ""))),
    "log_from_photo": (
        "Log from a photo of my notebook, whiteboard or cage card",
        [{"name": "what_it_shows", "description": "What the photo is of", "required": False}],
        lambda a: ("Read the photo I attached (my notebook, a whiteboard or cage cards) and record what it says in "
                   "BioManager: resolve every record, read numbers carefully and ask me about any you can't read, "
                   "then send one proposal and give me the link to approve it." +
                   (f"\n\nIt shows: {a['what_it_shows']}" if a.get("what_it_shows") else ""))),
    "plan_tomorrow": (
        "Plan tomorrow from what's due", [],
        lambda a: ("Look at what is due in BioManager over the next two days and plan my tomorrow: group the work by "
                   "room and time, say what each needs, and flag anything overdue. Don't propose changes unless I "
                   "ask.")),
}

# The prompts over the compute tools: BioManager works the numbers out.
PROMPTS.update({
    "weekly_review": (
        "Review the lab this week", [],
        lambda a: ("Review the lab this week with BioManager's weekly checks (lab_checks). Summarise what needs "
                   "attention by severity, highest first, naming each record with its link, and say which checks "
                   "found nothing. Then offer one proposal that clears the items that come with a fix (their "
                   "propose changes); send it only if I say yes, and give me the link to approve it.")),
    "design_experiment": (
        "Design an experiment",
        [{"name": "goal", "description": "What the experiment should find out", "required": True}],
        lambda a: ("Help me design this experiment from the lab's records in BioManager. Find the animals we have "
                   "(availability) and, if there aren't enough, how to breed them in time (breeding_plan); the "
                   "animals per group (power_analysis, with the SD from a past experiment's readouts if we have "
                   "one); a balanced, seeded allocation (randomize); and the procedures from the lab's saved "
                   "regimens (list regimens). Take doses only from the lab's regimens or a source you cite, and "
                   "leave the check against our animal protocol (IACUC) to me. Give me the design with every number "
                   "as BioManager worked it out and every assumption it made. Don't propose any change unless I ask."
                   "\n\nThe goal: " + a.get("goal", ""))),
    "write_methods": (
        "Write the methods for an experiment",
        [{"name": "experiment", "description": "The experiment's name or id", "required": True}],
        lambda a: ("Write the methods for this experiment from BioManager's records: resolve it, call "
                   "experiment_summary, and write the animals, procedures, outcome measure and statistics as a "
                   "methods paragraph in the past tense, using only what it returns. Then give the ARRIVE 2.0 "
                   "Essential 10 checklist, each item with what the records say and what is missing, and ask me for "
                   "the missing facts. Never invent a fact, number, supplier or lot.\n\nThe experiment: "
                   + a.get("experiment", ""))),
})
