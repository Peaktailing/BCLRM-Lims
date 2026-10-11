"""Captures (app/captures.py): what a person wrote down or photographed at
the bench, kept at once and read later by their assistant (the API and the
get_capture tool, whose photo is MCP image content)."""
from __future__ import annotations

import base64
import io
from datetime import date, timedelta
from unittest import mock

from tests.base import flashes, location, one, uniq
from tests.test_api import Base

from app import captures

# A 1×1 PNG.
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


class CaptureCase(Base):
    def capture(self, client=None, text="", file=None, **form):
        data = {"text": text, **form}
        if file is not None:
            name, body = file
            data["file"] = (io.BytesIO(body), name)
        return (client or self.m).post("/captures/new", data=data, content_type="multipart/form-data")

    def newest(self, username=None) -> int:
        return one("select max(id) from captures where owner_username=?", username or self.member)


class Capturing(CaptureCase):
    def test_a_line_is_kept_at_once_for_its_person_only(self):
        r = self.capture(text="Weaned cage 88: 4 F, 3 M")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(location(r), "/captures")
        cid = self.newest()
        self.assertEqual(one("select status from captures where id=?", cid), "waiting")
        page = self.get_ok(self.m, "/captures")
        self.assertIn("Weaned cage 88: 4 F, 3 M", page)
        self.assertIn(f"/captures/{cid}/dismiss", page)
        self.assertNotIn("Weaned cage 88: 4 F, 3 M", self.get_ok(self.o, "/captures"))
        self.assertNotIn("Weaned cage 88: 4 F, 3 M", self.get_ok(self.a, "/captures"))   # an admin neither
        self.assertIn('href="/captures"', self.get_ok(self.m, "/home"))                  # the account menu
        # Someone else can't dismiss it.
        self.assertEqual(self.o.post(f"/captures/{cid}/dismiss").status_code, 404)
        self.post(self.m, f"/captures/{cid}/dismiss")
        self.assertEqual(one("select status from captures where id=?", cid), "dismissed")
        self.post(self.m, f"/captures/{cid}/restore")
        self.assertEqual(one("select status from captures where id=?", cid), "waiting")

    def test_nothing_or_a_wrong_file_is_refused(self):
        before = one("select count(*) from captures")
        r = self.capture(text="  ")
        self.assertEqual(r.status_code, 400)
        self.assertIn(("error", "Write something or add a photo first."), flashes(r))
        r = self.capture(text="x", file=("tool.exe", b"MZ"))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(one("select count(*) from captures"), before)

    def test_a_photo_and_a_csv_are_kept_and_shown_to_their_person(self):
        self.capture(text="the card", file=("card.png", PNG))
        photo = self.newest()
        self.assertEqual(one("select file_type from captures where id=?", photo), "image/png")
        with self.m.get(f"/captures/{photo}/file") as r:
            self.assertEqual((r.status_code, r.mimetype, r.data), (200, "image/png", PNG))
        self.assertEqual(self.o.get(f"/captures/{photo}/file").status_code, 404)
        self.assertIn(f'src="/captures/{photo}/file"', self.get_ok(self.m, "/captures"))
        self.capture(file=("balance.csv", b"mouse,grams\n1043,21.5\n"))
        sheet = self.newest()
        self.assertEqual(one("select file_type from captures where id=?", sheet), "text/csv")
        with self.m.get(f"/captures/{sheet}/file?view=1") as r:
            self.assertEqual(r.mimetype, "text/plain")          # a file is never run as a page

    def test_where_it_was_taken(self):
        code = uniq("88")
        cage = self.make_cage(self.m, code)
        self.capture(text="at the cage", kind="cage", id=str(cage))
        self.assertEqual(one("select at_label from captures where id=?", self.newest()), f"Cage {code}")
        # A card scanned on the page: its link opens the cage's row.
        self.capture(text="scanned", card=f"http://localhost/colony?view=cages&scope=all&card=1#cage-{cage}")
        self.assertEqual(one("select at_kind || ':' || at_id from captures where id=?", self.newest()),
                         f"cage:{cage}")
        self.capture(text="nothing there", kind="cage", id="999999999")
        self.assertEqual(one("select at_kind from captures where id=?", self.newest()), "")
        self.assertEqual(captures.from_card("http://x/experiments/12/bench"), ("experiment", 12))
        self.assertEqual(captures.from_card("http://x/stocks/flies?view=vials#unit-7"), ("stock_unit", 7))

    def test_bench_mode_offers_capture(self):
        r = self.a.post("/experiments/in/zebrafish/create", data={
            "name": uniq("Exp "), "start_date": (date.today() - timedelta(days=2)).isoformat()})
        exp = int(location(r).rsplit("/", 1)[1])
        html = self.get_ok(self.a, f"/experiments/{exp}/bench")
        self.assertIn(f"/captures/new?kind=experiment&amp;id={exp}", html)
        page = self.get_ok(self.a, f"/captures/new?kind=experiment&id={exp}&back=/experiments/{exp}/bench")
        self.assertIn("At Experiment ", page)
        r = self.capture(self.a, text="dosed group B", kind="experiment", id=str(exp), back=f"/experiments/{exp}/bench")
        self.assertEqual(location(r), f"/experiments/{exp}/bench")
        self.assertEqual(one("select at_kind from captures where id=?", self.newest(self.admin)), "experiment")
        r = self.capture(self.a, text="elsewhere", back="//evil.example/")
        self.assertEqual(location(r), "/captures")


class ForTheAssistant(CaptureCase):
    def test_the_api_lists_and_reads_only_your_own(self):
        self.capture(text="dosed 12 mice")
        text = self.newest()
        self.capture(file=("card.png", PNG))
        photo = self.newest()
        self.capture(file=("balance.csv", "mouse,grams\n1043,21.5\n".encode()))
        sheet = self.newest()
        self.capture(self.o, text="someone else's")
        tok = self.token(self.m, scope="propose")
        listed = self.call("get", "/captures", tok).get_json()["data"]
        ids = [c["id"] for c in listed]
        self.assertTrue({text, photo, sheet} <= set(ids))
        self.assertNotIn(self.newest(self.other), ids)
        self.assertEqual(ids, sorted(ids, reverse=True))
        got = self.call("get", f"/captures/{text}", tok).get_json()
        self.assertEqual((got["text"], got["status"], got["file"]), ("dosed 12 mice", "waiting", None))
        got = self.call("get", f"/captures/{photo}", tok).get_json()
        self.assertEqual(got["image"]["mimeType"], "image/png")
        self.assertTrue(base64.b64decode(got["image"]["data"]))
        got = self.call("get", f"/captures/{sheet}", tok).get_json()
        self.assertEqual(got["file_text"], "mouse,grams\n1043,21.5\n")
        self.assertEqual(self.call("get", f"/captures/{self.newest(self.other)}", tok).status_code, 404)
        self.assertEqual(self.call("get", "/captures?status=nonsense", tok).status_code, 400)
        self.post(self.m, f"/captures/{text}/dismiss")
        self.assertNotIn(text, [c["id"] for c in self.call("get", "/captures", tok).get_json()["data"]])
        self.assertIn(text, [c["id"] for c in self.call("get", "/captures?status=dismissed", tok).get_json()["data"]])

    def test_a_big_photo_without_pillow_is_refused_with_a_message(self):
        self.capture(file=("card.png", PNG))
        photo = self.newest()
        tok = self.token(self.m, scope="read")
        with mock.patch.object(captures, "_pil", return_value=None), \
                mock.patch.object(captures, "SEND_IMAGE_MAX", 10):
            got = self.call("get", f"/captures/{photo}", tok).get_json()
        self.assertNotIn("image", got)
        self.assertIn("too big to send", got["file_note"])

    def test_get_capture_over_mcp_is_an_image(self):
        self.capture(text="cage card", file=("card.png", PNG))
        photo = self.newest()
        tok = self.token(self.m, scope="propose", label="Claude")
        rpc = lambda method, params: self.bare.post(  # noqa: E731
            "/api/v1/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            headers={"Authorization": f"Bearer {tok}"}).get_json()["result"]
        tools = {t["name"]: t for t in rpc("tools/list", {})["tools"]}
        self.assertTrue(tools["get_capture"]["annotations"]["readOnlyHint"])
        self.assertTrue(tools["list_captures"]["annotations"]["readOnlyHint"])
        listed = rpc("tools/call", {"name": "list_captures", "arguments": {}})
        self.assertIn(photo, [c["id"] for c in listed["structuredContent"]["captures"]])
        out = rpc("tools/call", {"name": "get_capture", "arguments": {"capture_id": photo}})
        self.assertFalse(out["isError"])
        self.assertEqual(out["content"][0]["type"], "text")
        self.assertIn("cage card", out["content"][0]["text"])
        image = out["content"][1]
        self.assertEqual((image["type"], image["mimeType"]), ("image", "image/png"))
        self.assertTrue(base64.b64decode(image["data"]))
        self.assertNotIn("_content", out["structuredContent"])
        self.assertNotIn("image", out["structuredContent"])
        prompts = [p["name"] for p in rpc("prompts/list", {})["prompts"]]
        self.assertIn("process_captures", prompts)
