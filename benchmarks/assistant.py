#!/usr/bin/env python3
"""How accurately an AI assistant turns what a lab member says into records.

    python -m pip install -r benchmarks/requirements.txt
    .venv/bin/python benchmarks/assistant.py                       # every scenario, claude-opus-5-5
    .venv/bin/python benchmarks/assistant.py --model claude-sonnet-5-5 --repeat 3
    .venv/bin/python benchmarks/assistant.py --only litter,move --show
    .venv/bin/python benchmarks/assistant.py --check               # the scenarios and tools, no model

Each scenario makes a small lab of its own (cages, mice, a reagent…) through
the app's own pages, as the tests do, then gives the assistant what a person
says ("Litter in cage 202 yesterday, 7 pups"). The assistant has exactly the
tools an assistant app gets over MCP (app/assistant_tools.py, called as the
person with a Read and propose token) and the plugin's skill as its
instructions (--context: the skill, only the server's instructions, or
none). When it asks the person something, the scenario answers as the
person would, or says they don't know. Then its proposal is approved, as the
person would press Approve, and the records are compared with the truth:

  correct   every record is as it should be, and nothing else changed;
  asked     it asked rather than guessed, and changed nothing wrongly
            (the right outcome where the words alone can't say);
  missing   something said wasn't recorded (no proposal, or a part left out);
  wrong     a record ended up wrong, silently: the number that must stay 0.

It runs on a throwaway database (tests/base.py), so no lab's data is opened,
and it needs an Anthropic API key (ANTHROPIC_API_KEY, or a profile from
`ant auth login`). Results go to benchmarks/results/assistant-<version>-<model>.md
and .json. Model runs vary: use --repeat to see how much.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("BIOMANAGER_TELEMETRY", "0")

# tests.base first: it points the app at a throwaway database before app is imported.
from tests.base import AppTestCase, client_for, make_user, one, rows  # noqa: E402
from app import assistant_tools as tools  # noqa: E402
from app import proposals  # noqa: E402
from app.app import app  # noqa: E402
from app.db import SessionLocal  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
SKILL = ROOT / "plugins" / "biomanager" / "skills" / "biomanager" / "SKILL.md"
TODAY = date.today()
OUTCOMES = ("correct", "asked", "missing", "wrong", "error")


def day(n: int = 0) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


# ---------------------------------------------------------------- the lab, as the assistant reaches it

class LabApi(tools.Api):
    """BioManager's /api/v1 inside this process, with the person's token."""

    def __init__(self, token: str):
        super().__init__("http://localhost", token)
        self.client = app.test_client()

    def request(self, method, path, query=None, body=None):
        r = self.client.open(f"/api/v1/{path.lstrip('/')}", method=method, json=body,
                             query_string={k: v for k, v in (query or {}).items() if v not in (None, "")},
                             headers={"Authorization": f"Bearer {self.token}"})
        data = r.get_json(silent=True)
        if r.status_code >= 400:
            raise tools.ApiError((data or {}).get("error") or f"BioManager answered {r.status_code}.")
        return data


def propose_token(client) -> str:
    r = client.post("/settings/api-tokens", data={"label": "Benchmark assistant", "scope": "propose", "expires": "30"})
    found = re.search(r'id="api-token"[^>]*>(bmt_\w+)<', r.get_data(as_text=True))
    if not found:
        raise SystemExit("Couldn't make a Read and propose token for the benchmark's person.")
    return found.group(1)


# ---------------------------------------------------------------- scenarios

make = AppTestCase  # its record factories are static methods: make.make_cage(client, …)


@dataclass
class Lab:
    """What a scenario made: the person and the records its checks look at."""
    username: str
    client: object
    ids: dict = field(default_factory=dict)


@dataclass
class Scenario:
    name: str
    says: str                                   # the person's first message ({names} filled from the lab)
    build: Callable[[Lab], None]                # makes the records
    check: Callable[[Lab], list[str]]           # after approving: what is wrong ([] = right)
    answers: dict = field(default_factory=dict)  # a word in the assistant's question → the person's reply
    expect_change: bool = True                  # False: the right outcome changes nothing
    expect_question: bool = False               # True: the words can't say, so it should ask
    reply_check: Callable[[str], list[str]] | None = None   # its last message, where the reply is the point


def mouse_number(row_id: int) -> int:
    return one("select mouse_id from mice where id=?", row_id)


def cage_of(row_id: int) -> str:
    return one("select c.cage_id from mice m join mouse_cages c on c.id=m.cage_id_fk where m.id=?", row_id) or ""


def _breeding_cage(lab: Lab, code: str, **fields) -> None:
    lab.ids[code] = make.make_cage(lab.client, code, purpose="Breeding", **fields)


def _mouse(lab: Lab, name: str, cage: str, **fields) -> None:
    lab.ids[name] = make.make_mouse(lab.client, lab.username, cage=cage, date_of_birth=day(120), **fields)


def vague_build(lab: Lab) -> None:
    _breeding_cage(lab, "110", date_give_birth=day(21))
    _mouse(lab, "dam", "110", gender="F", status="breeding")


def litter_build(lab: Lab) -> None:
    _breeding_cage(lab, "202")
    _mouse(lab, "dam", "202", gender="F", status="breeding")
    _mouse(lab, "sire", "202", gender="M", status="breeding")


def litter_check(lab: Lab) -> list[str]:
    born = one("select date_give_birth from mouse_cages where id=?", lab.ids["202"])
    return [] if str(born)[:10] == day(1) else [f"cage 202's litter date is {born}, not {day(1)}"]


def move_build(lab: Lab) -> None:
    make.make_cage(lab.client, "288")
    make.make_cage(lab.client, "291")
    for name in ("a", "b", "c"):
        _mouse(lab, name, "288", gender="F")


def move_check(lab: Lab) -> list[str]:
    wrong = [f"mouse {mouse_number(lab.ids[n])} is in cage {cage_of(lab.ids[n])}, not 291"
             for n in ("a", "b") if cage_of(lab.ids[n]) != "291"]
    if cage_of(lab.ids["c"]) != "288":
        wrong.append(f"mouse {mouse_number(lab.ids['c'])} moved too, to {cage_of(lab.ids['c'])}")
    return wrong


def weight_build(lab: Lab) -> None:
    make.make_cage(lab.client, "305")
    _mouse(lab, "a", "305", gender="M")
    _mouse(lab, "b", "305", gender="M")


def weight_check(lab: Lab) -> list[str]:
    got = rows("select grams, weigh_date from mouse_weights where mouse_id_fk=? order by id", lab.ids["a"])
    other = rows("select grams from mouse_weights where mouse_id_fk=?", lab.ids["b"])
    right = [(float(g), str(d)[:10]) for g, d in got] == [(24.1, day(0))]
    wrong = [] if right else [f"weights {got}, not 24.1 g today"]
    return wrong + ([f"the other mouse was weighed too: {other}"] if other else [])


def died_build(lab: Lab) -> None:
    make.make_cage(lab.client, "412")
    _mouse(lab, "a", "412", gender="F")
    _mouse(lab, "b", "412", gender="F")


def died_check(lab: Lab) -> list[str]:
    status, died = one("select status from mice where id=?", lab.ids["a"]), \
        one("select date_of_death from mice where id=?", lab.ids["a"])
    wrong = [] if status == "sac" and str(died)[:10] == day(0) else [f"mouse is {status}, died {died}"]
    if one("select status from mice where id=?", lab.ids["b"]) == "sac":
        wrong.append("its cage mate was marked dead too")
    return wrong


def ambiguous_build(lab: Lab) -> None:
    _breeding_cage(lab, "502")
    make.make_cage(lab.client, "591")
    _mouse(lab, "a", "502", gender="M", status="breeding")
    _mouse(lab, "b", "502", gender="M", status="breeding")


def ambiguous_check(lab: Lab) -> list[str]:
    moved = [mouse_number(lab.ids[n]) for n in ("a", "b") if cage_of(lab.ids[n]) == "591"]
    return [f"it guessed and moved {moved}"] if moved else []


def unknown_build(lab: Lab) -> None:
    make.make_cage(lab.client, "611")
    _mouse(lab, "a", "611", gender="F")


def unknown_check(lab: Lab) -> list[str]:
    return [f"something was recorded for a cage that doesn't exist: {n} new cages"
            for n in [one("select count(*) from mouse_cages where cage_id='699'")] if n]


def vague_reply(text: str) -> list[str]:
    return [] if "110" in text else ["it didn't show what's due (the weaning in cage 110)"]


SCENARIOS = [
    Scenario("vague", "I want to change something in BioManager", vague_build, lambda lab: [],
             expect_change=False, reply_check=vague_reply),
    Scenario("litter", "Litter in cage 202 yesterday, 7 pups.", litter_build, litter_check),
    Scenario("move", "Moved {a} and {b} from cage 288 to 291 this morning.", move_build, move_check),
    Scenario("weight", "Weighed {a}: 24.1 g.", weight_build, weight_check),
    Scenario("died", "{a} in cage 412 was found dead this morning.", died_build, died_check),
    Scenario("ambiguous", "Moved the breeder from 502 to 591.", ambiguous_build, ambiguous_check,
             answers={"which": "Sorry, I don't remember which one. Leave it for now."},
             expect_change=False, expect_question=True),
    Scenario("unknown", "Weaned cage 699 today, 6 pups.", unknown_build, unknown_check,
             answers={"": "Oh, I must have the wrong number. Never mind."},
             expect_change=False, expect_question=True),
]


# ---------------------------------------------------------------- the conversation

def tool_list(api) -> list[dict]:
    return [{"name": name, "description": tools.description(api, name), "input_schema": schema}
            for name, (_d, schema, _f) in tools.TOOLS.items()]


def system_prompt(context: str) -> str:
    base = "You are a helpful assistant. The person you are helping works in a research lab."
    if context == "skill":
        text = SKILL.read_text(encoding="utf-8")
        return base + "\n\n" + re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    if context == "instructions":
        return base + "\n\n" + tools.INSTRUCTIONS
    return base


def person_reply(scenario: Scenario, question: str) -> str:
    low = question.lower()
    for word, reply in scenario.answers.items():
        if word in low:
            return reply
    return "I don't know. Leave anything you're unsure of out."


def converse(client, model: str, effort: str, context: str, scenario: Scenario, api, says: str,
             show: bool) -> dict:
    """One conversation: the assistant's turns, its tool calls, and the person's replies."""
    import anthropic

    messages = [{"role": "user", "content": says}]
    calls, questions, turns, usage = [], 0, 0, {"input": 0, "output": 0}
    last_text = ""
    tool_defs = tool_list(api)
    while turns < 40:
        turns += 1
        try:
            response = client.messages.create(model=model, max_tokens=16000, system=system_prompt(context),
                                              tools=tool_defs, messages=messages,
                                              output_config={"effort": effort})
        except anthropic.APIStatusError as e:
            return {"error": f"API {e.status_code}: {e.message}", "calls": calls}
        usage["input"] += response.usage.input_tokens
        usage["output"] += response.usage.output_tokens
        if response.stop_reason == "refusal":
            return {"error": "the model declined", "calls": calls, "usage": usage}
        if response.stop_reason == "max_tokens":
            return {"error": "the reply ran past max_tokens", "calls": calls, "usage": usage}
        messages.append({"role": "assistant", "content": response.content})
        text = " ".join(b.text for b in response.content if b.type == "text").strip()
        if text:
            last_text = text
            if show:
                print(f"    assistant: {text[:400]}")
        uses = [b for b in response.content if b.type == "tool_use"]
        if uses:
            results = []
            for use in uses:
                out = tools.call_tool(api, use.name, dict(use.input))
                calls.append({"tool": use.name, "input": use.input, "error": out.get("error")})
                if show:
                    print(f"    → {use.name}({json.dumps(use.input, ensure_ascii=False)[:200]})")
                results.append({"type": "tool_result", "tool_use_id": use.id,
                                "content": json.dumps(out, ensure_ascii=False, default=str),
                                **({"is_error": True} if "error" in out else {})})
            messages.append({"role": "user", "content": results})
            continue
        # It stopped to talk: a question gets the person's answer (at most three), else it's done.
        if "?" in text and questions < 3:
            questions += 1
            reply = person_reply(scenario, text)
            if show:
                print(f"    person: {reply}")
            messages.append({"role": "user", "content": reply})
            continue
        break
    return {"calls": calls, "questions": questions, "last": last_text, "usage": usage}


# ---------------------------------------------------------------- scoring

def run_one(client, args, scenario: Scenario, n: int) -> dict:
    username = make_user(f"bench{scenario.name}{n}{int(time.time() * 1000) % 100000}")
    lab = Lab(username, client_for(username))
    scenario.build(lab)
    names = {k: mouse_number(v) for k, v in lab.ids.items()
             if isinstance(v, int) and one("select 1 from mice where id=?", v)}
    says = scenario.says.format(**{k: f"mouse {v}" for k, v in names.items()})
    api = LabApi(propose_token(lab.client))
    talk = converse(client, args.model, args.effort, args.context, scenario, api, says, args.show)
    out = {"scenario": scenario.name, "says": says, **{k: v for k, v in talk.items() if k != "last"}}
    if "error" in talk:
        return {**out, "outcome": "error", "why": [talk["error"]]}
    problems = []
    with SessionLocal() as s:
        pending = rows("select id from proposals where owner_username=? and status='pending' order by id", username)
        if len(pending) > 1:
            problems.append(f"{len(pending)} proposals left waiting; the newest was approved")
        if pending:
            try:
                proposals.approve(app, s, pending[-1][0], username)
                s.commit()
            except proposals.ProposalError as e:
                problems.append(f"approving failed: {e}")
    wrong = scenario.check(lab)
    if scenario.reply_check:
        wrong += scenario.reply_check(talk.get("last", ""))
    proposed = bool(pending)
    if wrong and (proposed or scenario.reply_check):
        outcome = "wrong" if proposed else "missing"
    elif scenario.expect_change and not proposed:
        outcome, wrong = "missing", ["nothing was proposed"]
    elif scenario.expect_question and talk["questions"] == 0 and not proposed:
        outcome = "asked" if not wrong else "wrong"        # it declined without asking: still safe
    elif scenario.expect_question:
        outcome = "asked"
    else:
        outcome = "correct"
    if not scenario.expect_change and proposed and not wrong:
        problems.append("it proposed something where nothing needed changing")
    return {**out, "outcome": outcome, "why": wrong + problems}


def summary(results: list[dict]) -> dict:
    by = {}
    for r in results:
        by.setdefault(r["scenario"], {o: 0 for o in OUTCOMES})[r["outcome"]] += 1
    total = {o: sum(c[o] for c in by.values()) for o in OUTCOMES}
    return {"by_scenario": by, "total": total, "runs": len(results)}


def version() -> str:
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                                text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "nogit"
    try:
        from desktop_updates import version as app_version
        v = app_version()
    except Exception:  # noqa: BLE001 - only names the file
        v = "dev"
    return f"{v}-{commit}"


def write(results: list[dict], args) -> Path:
    RESULTS.mkdir(exist_ok=True)
    stem = RESULTS / f"assistant-{version()}-{args.model}-{args.context}"
    data = {"model": args.model, "effort": args.effort, "context": args.context, "date": TODAY.isoformat(),
            "summary": summary(results), "runs": results}
    stem.with_suffix(".json").write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str),
                                         encoding="utf-8")
    s = data["summary"]
    lines = [f"# Assistant benchmark: {args.model} ({args.context}, effort {args.effort})", "",
             f"{s['runs']} conversations, {TODAY.isoformat()}.", "",
             "| Scenario | " + " | ".join(OUTCOMES) + " |", "| --- |" + " ---: |" * len(OUTCOMES)]
    for name, counts in s["by_scenario"].items():
        lines.append(f"| {name} | " + " | ".join(str(counts[o]) for o in OUTCOMES) + " |")
    lines.append("| **All** | " + " | ".join(f"**{s['total'][o]}**" for o in OUTCOMES) + " |")
    lines += ["", "## What went wrong", ""]
    lines += [f"- {r['scenario']}: {'; '.join(r['why'])}" for r in results if r["why"]] or ["Nothing."]
    stem.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return stem.with_suffix(".md")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="medium", choices=("low", "medium", "high", "xhigh", "max"))
    ap.add_argument("--context", default="skill", choices=("skill", "instructions", "none"),
                    help="what the assistant knows of BioManager: the plugin's skill (default), only the "
                         "server's instructions, or nothing but the tools")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--only", default="", help="scenarios, comma-separated")
    ap.add_argument("--show", action="store_true", help="print each conversation")
    ap.add_argument("--check", action="store_true", help="build each scenario's lab and list the tools; no model")
    args = ap.parse_args()
    chosen = [s for s in SCENARIOS if not args.only or s.name in args.only.split(",")]
    if args.check:
        for i, sc in enumerate(chosen):
            username = make_user(f"check{sc.name}{i}")
            lab = Lab(username, client_for(username))
            sc.build(lab)
            api = LabApi(propose_token(lab.client))
            print(f"{sc.name}: lab built ({len(lab.ids)} records); {len(tool_list(api))} tools; "
                  f"overview has {len(tools.lab_overview(api)['due_today'])} due today")
        return
    import anthropic
    client = anthropic.Anthropic()
    results = []
    for n in range(args.repeat):
        for sc in chosen:
            print(f"{sc.name} ({n + 1}/{args.repeat})")
            r = run_one(client, args, sc, n)
            print(f"  {r['outcome']}" + (f": {'; '.join(r['why'])}" if r["why"] else ""))
            results.append(r)
    print(f"\n{summary(results)['total']}\nwrote {write(results, args).relative_to(ROOT)}")


if __name__ == "__main__":
    main()
