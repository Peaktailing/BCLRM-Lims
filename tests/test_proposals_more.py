"""Proposed changes, continued (app/proposals.py): each change's evidence,
Send back with a reason, and proposals made from captures (app/captures.py)."""
from __future__ import annotations

import base64
import io
import json

from tests.base import days_ago, flashes, one, row
from tests.test_api import Base

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def litter(cage: int, day: str, evidence=None) -> dict:
    change = {"action": "litter_born", "target": {"kind": "cage", "id": cage}, "fields": {"date": day}}
    if evidence is not None:
        change["evidence"] = evidence
    return change


class More(Base):
    def propose(self, *changes, client=None, **extra):
        tok = self.token(client or self.m, scope="propose")
        return self.call("post", "/proposals", tok, json={"summary": "From my notes", "source": "Claude",
                                                         "changes": list(changes), **extra}), tok

    def capture(self, client, text="", png=False) -> int:
        data = {"text": text}
        if png:
            data["photo"] = (io.BytesIO(PNG), "card.png")
        client.post("/captures/new", data=data, content_type="multipart/form-data")
        return one("select max(id) from captures")

    def test_each_change_shows_its_evidence_and_still_runs(self):
        cage, other = self.make_cage(self.m), self.make_cage(self.m)
        r, tok = self.propose(litter(cage, days_ago(1), "litter in 88 yesterday, 7 pups"),
                              litter(other, days_ago(2), {"quote": "  second   litter  " + "x" * 400,
                                                          "where": "line 3"}))
        self.assertEqual(r.status_code, 201, r.get_json())
        body = r.get_json()
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["changes"][0]["evidence"], {"quote": "litter in 88 yesterday, 7 pups", "capture": None,
                                                          "where": ""})
        quote = body["changes"][1]["evidence"]["quote"]
        self.assertTrue(quote.startswith("second litter x") and quote.endswith("…") and len(quote) == 300)
        full = self.call("get", f"/proposals/{body['id']}", tok).get_json()
        self.assertEqual(full["changes"][0]["request"]["evidence"], "litter in 88 yesterday, 7 pups")
        page = self.get_ok(self.m, "/proposals")
        self.assertIn("From your notes: “litter in 88 yesterday, 7 pups”", page)
        self.post(self.m, f"/proposals/{body['id']}/approve")
        self.assertEqual(one("select status from proposals where id=?", body["id"]), "approved")
        self.assertEqual(str(one("select date_give_birth from mouse_cages where id=?", cage))[:10], days_ago(1))

    def test_send_back_with_a_reason_and_the_assistant_reads_it(self):
        cage = self.make_cage(self.m)
        r, tok = self.propose(litter(cage, days_ago(1)))
        pid = r.get_json()["id"]
        self.assertIn(f"/proposals/{pid}/send-back", self.get_ok(self.m, "/proposals"))
        r = self.post(self.m, f"/proposals/{pid}/send-back", {"reason": "  "})
        self.assertIn(("error", "Say in a line what to correct."), flashes(r))
        self.assertEqual(one("select status from proposals where id=?", pid), "pending")
        # Only its person sends it back.
        self.post(self.o, f"/proposals/{pid}/send-back", {"reason": "no"})
        self.assertEqual(one("select status from proposals where id=?", pid), "pending")
        notes = one("select count(*) from notifications where recipient_username=?", self.member)
        r = self.post(self.m, f"/proposals/{pid}/send-back", {"reason": "It was cage 89, not 88"})
        self.assertTrue([t for c, t in flashes(r) if c == "success"])
        self.assertEqual(row("select status, reason from proposals where id=?", pid),
                         ("sent_back", "It was cage 89, not 88"))
        self.assertEqual(one("select count(*) from notifications where recipient_username=?", self.member), notes)
        self.assertIn("Sent back: “It was cage 89, not 88”", r.get_data(as_text=True))
        got = self.call("get", f"/proposals/{pid}", tok).get_json()
        self.assertEqual(got["reason"], "It was cage 89, not 88")
        self.assertIn("replaces", got["next"])
        self.assertIn(pid, [p["id"] for p in self.call("get", "/proposals?status=sent_back", tok).get_json()["data"]])
        # Not approved, nor sent back twice; a corrected one replaces it.
        r = self.post(self.m, f"/proposals/{pid}/approve")
        self.assertIn("can't be approved", " ".join(t for _c, t in flashes(r)))
        self.assertIsNone(one("select date_give_birth from mouse_cages where id=?", cage))
        r, _ = self.propose(litter(cage, days_ago(2)), replaces=pid)
        self.assertEqual(r.get_json()["status"], "pending")
        self.assertEqual(one("select status from proposals where id=?", pid), "sent_back")

    def test_made_from_captures_they_are_used_when_approved(self):
        photo = self.capture(self.m, "litter in my cage", png=True)
        line = self.capture(self.m, "and this line")
        cage = self.make_cage(self.m)
        r, tok = self.propose(litter(cage, days_ago(1), {"quote": "litter in my cage", "capture": line}),
                              captures=[photo])
        self.assertEqual(r.status_code, 201, r.get_json())
        pid = r.get_json()["id"]
        self.assertEqual(sorted(r.get_json()["captures"]), sorted([photo, line]))
        page = self.get_ok(self.m, "/proposals")
        self.assertIn(f"From capture #{photo}", page)
        self.assertIn(f'src="/captures/{photo}/file"', page)
        self.assertIn(f"Capture #{line}", page)
        self.assertEqual(one("select status from captures where id=?", photo), "waiting")
        self.post(self.m, f"/proposals/{pid}/approve")
        batch = one("select batch_id_fk from proposals where id=?", pid)
        self.assertTrue(batch)
        for capture in (photo, line):
            self.assertEqual(row("select status, proposal_id_fk, batch_id_fk from captures where id=?", capture),
                             ("used", pid, batch))
        self.assertIn(f"Used by proposal #{pid}", self.get_ok(self.m, "/captures"))

    def test_someone_elses_capture_is_refused(self):
        theirs = self.capture(self.o, "not yours")
        cage = self.make_cage(self.m)
        before = one("select count(*) from proposals")
        r, _ = self.propose(litter(cage, days_ago(1)), captures=[theirs])
        self.assertEqual(r.status_code, 400)
        self.assertIn(f"no capture {theirs}", r.get_json()["error"])
        r, _ = self.propose(litter(cage, days_ago(1), {"quote": "x", "capture": theirs}))
        self.assertEqual(r.status_code, 400)
        r, _ = self.propose(litter(cage, days_ago(1)), captures="1,2")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(one("select count(*) from proposals"), before)
        self.assertEqual(one("select status from captures where id=?", theirs), "waiting")

    def test_the_tools_say_how(self):
        from app import assistant_tools as tools
        self.assertIn("list_captures", tools.INSTRUCTIONS)
        self.assertIn("evidence", tools.INSTRUCTIONS)
        self.assertIn("evidence", tools.PROPOSE_HELP)
        self.assertIn("captures", json.dumps(tools.TOOLS["propose_changes"][1]))
        self.assertIn("process_captures", tools.PROMPTS)
