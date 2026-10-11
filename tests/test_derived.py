"""Derived readouts (app/derived.py): BioManager works the readout out from
what was measured (a tumour's length and width, each gene's Ct, a well's
OD), on the experiment page, in bench mode, through the API and a proposed
experiment_reading, and in the assistant's `derive` tool, which changes
nothing."""
from __future__ import annotations

import json
import math
import unittest
from datetime import date, timedelta

from tests.base import *  # noqa: F401,F403
from tests.base import AppTestCase, location, one, uniq

from app import actions, derived
from app.app import app

TODAY = date.today()


class Formulas(unittest.TestCase):
    def test_tumour_volume_both_conventions(self):
        self.assertEqual(derived.compute("tumour_lw", {"length": 12, "width": 8}), 384.0)
        self.assertEqual(derived.compute("tumour_lw", {"length": "10,5", "width": "4"}), 84.0)   # a comma as decimal point
        self.assertAlmostEqual(derived.compute("tumour_lwh", {"length": 10, "width": 8, "height": 6}),
                               math.pi / 6 * 480, places=3)
        self.assertEqual(derived.compute("tumour_lw", {"length": 0, "width": 0}), 0.0)          # gone is a reading

    def test_delta_ct_and_against_the_control(self):
        self.assertEqual(derived.compute("delta_ct", {"ct_target": 25.5, "ct_reference": 18}), 7.5)
        self.assertEqual(derived.compute("delta_ct", {"ct_target": 17, "ct_reference": 18}), -1.0)
        rows = [{"group": "Vehicle", "ct_target": 25, "ct_reference": 18},
                {"group": "vehicle ", "ct_target": 26, "ct_reference": 18},
                {"group": "Drug", "ct_target": 23, "ct_reference": 18}]
        out = derived.delta_delta_ct(rows, "Vehicle")
        self.assertEqual([r["control_mean_delta_ct"] for r in out], [7.5] * 3)
        self.assertEqual([r["delta_delta_ct"] for r in out], [-0.5, 0.5, -2.5])
        self.assertAlmostEqual(out[2]["fold_change"], 2 ** 2.5, places=4)
        self.assertEqual(derived.group_values("fold_change", rows, "Vehicle")[2], out[2]["fold_change"])
        # Each day against its own control.
        days = [{"group": "V", "day": "1", "ct_target": 20, "ct_reference": 18},
                {"group": "V", "day": "2", "ct_target": 22, "ct_reference": 18},
                {"group": "D", "day": "2", "ct_target": 21, "ct_reference": 18}]
        self.assertEqual([r["delta_delta_ct"] for r in derived.delta_delta_ct(days, "V")], [0.0, 0.0, -1.0])
        with self.assertRaisesRegex(derived.DerivedError, "No animal of the control group “Ctrl”"):
            derived.delta_delta_ct(rows, "Ctrl")
        with self.assertRaisesRegex(derived.DerivedError, "which group is the control"):
            derived.delta_delta_ct(rows, "")
        with self.assertRaisesRegex(derived.DerivedError, "against a control group"):
            derived.compute("fold_change", {"ct_target": 25, "ct_reference": 18})

    def test_percent_of_baseline_and_blank_subtracted(self):
        self.assertEqual(derived.compute("percent_of_baseline", {"value": 18, "baseline": 20}), 90.0)
        self.assertEqual(derived.compute("blank_subtracted", {"od": 0.85, "blank": 0.05}), 0.8)
        self.assertEqual(derived.compute("blank_subtracted", {"od": 0.04, "blank": 0.05}), -0.01)   # noise near blank

    def test_nonsense_is_refused_in_words(self):
        cases = [
            ("tumour_lw", {"length": 12}, "Width is missing"),
            ("tumour_lw", {"length": -1, "width": 1}, "can't be below zero"),
            ("tumour_lw", {"length": "abc", "width": 1}, "isn't a number"),
            ("tumour_lw", {"length": True, "width": 1}, "isn't a number"),
            ("tumour_lw", {"length": "nan", "width": 1}, "never came up"),
            ("tumour_lw", {"length": 5, "width": 8}, "the length is the longer side"),
            ("tumour_lw", {"length": 5, "width": 3, "depth": 2}, "not depth"),
            ("tumour_lw", 384, "give those, not the result"),
            ("delta_ct", {"ct_target": "Undetermined", "ct_reference": 18}, "never came up"),
            ("delta_ct", {"ct_target": 60, "ct_reference": 18}, "isn't one a run gives"),
            ("delta_ct", {"ct_target": 0, "ct_reference": 18}, "isn't one a run gives"),
            ("percent_of_baseline", {"value": 5, "baseline": 0}, "baseline above zero"),
            ("blank_subtracted", {"od": 12, "blank": 0.05}, "more than a plate reader reads"),
            ("cell_count", {"x": 1}, "not a formula"),
        ]
        for key, raw, words in cases:
            with self.subTest(key=key, raw=raw), self.assertRaisesRegex(derived.DerivedError, words):
                derived.compute(key, raw)

    def test_every_formula_says_what_it_takes(self):
        listed = {f["key"]: f for f in derived.catalogue()}
        self.assertEqual(set(listed), {"tumour_lw", "tumour_lwh", "delta_ct", "delta_delta_ct", "fold_change",
                                       "percent_of_baseline", "blank_subtracted"})
        self.assertEqual(listed["tumour_lw"]["unit"], "mm³")
        self.assertEqual([i["key"] for i in listed["tumour_lwh"]["inputs"]], ["length", "width", "height"])
        for f in listed.values():
            self.assertTrue(f["description"] and f["expression"] and f["inputs"], f["key"])

    def test_derive_over_rows_keeps_each_rows_own_answer(self):
        out = derived.derive("tumour_lw", [{"animal": "1043", "length": 12, "width": 8},
                                           {"animal": "1044", "inputs": {"length": 5, "width": 9}}])
        self.assertEqual(out["rows"][0]["value"], 384.0)
        self.assertIn("longer side", out["rows"][1]["error"])
        self.assertEqual((out["computed"], out["refused"], out["changes_nothing"]), (1, 1, True))
        with self.assertRaises(derived.DerivedError):
            derived.derive("tumour_lw", [])

    def test_the_inputs_kept_with_a_reading_read_back(self):
        text = derived.note({"length": 12.0, "width": 8.4})
        self.assertEqual(text, '{"length": 12, "width": 8.4}')
        self.assertEqual(derived.read_note(text), {"length": 12.0, "width": 8.4})
        self.assertIsNone(derived.read_note("weighed late"))
        self.assertEqual(derived.inputs_text("tumour_lw", {"length": 12, "width": 8}), "Length 12 mm, Width 8 mm")


class Base(AppTestCase):
    def colony_experiment(self, groups=("Vehicle", "Vehicle", "Drug")):
        r = self.m.post("/colony/experiments/create", data={"name": uniq("Xeno "),
                                                            "start_date": (TODAY - timedelta(days=3)).isoformat()})
        exp = int(location(r).rsplit("/", 1)[1])
        keys = []
        for group in groups:
            mouse = self.make_mouse(self.m, self.member)
            self.m.post(f"/colony/experiments/{exp}/add-mouse", data={"mouse_row_id": mouse, "treatment_group": group})
            keys.append(f"mouse:{mouse}")
        return exp, keys

    def choose(self, exp, readout, control=""):
        r = self.m.post(f"/experiments/{exp}/update", data={"readout": readout, "readout_control": control},
                        headers={"X-Autosave": "1"})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True)[:300])
        return r.get_json()

    def read(self, exp, values, on=TODAY):
        return self.m.post(f"/experiments/{exp}/readings", json={"on": on.isoformat(), "values": values})


class OnThePage(Base):
    def test_the_readout_select_offers_them_and_the_unit_follows(self):
        exp, _keys = self.colony_experiment()
        html = self.get_ok(self.m, f"/colony/experiments/{exp}")
        self.assertIn("Worked out by BioManager from what you measure", html)
        self.assertIn('value="derived:tumour_lw"', html)
        self.assertIn("Tumour volume (L × W² / 2) (mm³)", html)
        data = self.choose(exp, "derived:tumour_lw")
        self.assertEqual(json.loads(one("select readout from experiments where id=?", exp)),
                         {"key": "derived", "formula": "tumour_lw"})
        self.assertEqual((data["readout"]["key"], data["readout"]["unit"], data["readout"]["verb"]),
                         ("derived:tumour_lw", "mm³", "Measure"))
        self.assertEqual([i["key"] for i in data["readout"]["inputs"]], ["length", "width"])
        self.assertIn("Control group", self.get_ok(self.m, f"/colony/experiments/{exp}"))
        # The lab's other convention.
        self.assertEqual(self.choose(exp, "derived:tumour_lwh")["readout"]["inputs"][2]["key"], "height")

    def test_lengths_and_widths_in_a_volume_out_nothing_lost(self):
        exp, keys = self.colony_experiment()
        self.choose(exp, "derived:tumour_lw")
        r = self.read(exp, {keys[0]: {"length": "12", "width": "8"}, keys[1]: {"length": "10", "width": "6"}})
        self.assertEqual(r.status_code, 200, r.get_json())
        table = r.get_json()["table"]
        row = next(x for x in table["rows"] if x["key"] == keys[0])
        self.assertEqual((row["values"], row["inputs"]), ([384.0], [{"length": 12.0, "width": 8.0}]))
        self.assertEqual(one("select note from experiment_readings where experiment_id_fk=? and subject=?", exp, keys[0]),
                         '{"length": 12, "width": 8}')
        self.assertEqual(one("select readout_key from experiment_readings where experiment_id_fk=? and subject=?",
                             exp, keys[0]), "derived:tumour_lw")
        # A number typed for it, or a width longer than the length, is refused in words.
        plain = self.read(exp, {keys[2]: "384"})
        self.assertEqual(plain.status_code, 400)
        self.assertIn("give those, not the result", plain.get_json()["error"])
        wrong = self.read(exp, {keys[2]: {"length": "5", "width": "9"}})
        self.assertIn("the length is the longer side", wrong.get_json()["error"])
        # Blank removes it.
        self.read(exp, {keys[1]: {"length": "", "width": ""}})
        self.assertIsNone(one("select value from experiment_readings where experiment_id_fk=? and subject=?", exp, keys[1]))
        # The export keeps what was measured beside each volume.
        csv = self.m.get(f"/experiments/{exp}/export.csv").get_data(as_text=True)
        self.assertIn("Length (mm),Width (mm)", csv.splitlines()[0])
        self.assertIn(",12.0,8.0", csv)

    def test_bench_mode_gets_the_inputs(self):
        exp, keys = self.colony_experiment()
        self.choose(exp, "derived:tumour_lw")
        self.read(exp, {keys[0]: {"length": "12", "width": "8"}})
        html = self.get_ok(self.m, f"/experiments/{exp}/bench")
        data = json.loads(html.split('id="xb-data">', 1)[1].split("</script>", 1)[0])
        self.assertEqual(data["readout"]["formula"], "tumour_lw")
        self.assertEqual(data["table"]["rows"][0]["inputs"], [{"length": 12.0, "width": 8.0}])

    def test_fold_change_against_the_control_groups_mean_that_day(self):
        exp, (v1, v2, drug) = self.colony_experiment()
        data = self.choose(exp, "derived:fold_change", control="Vehicle")
        self.assertEqual((data["readout"]["control"], data["readout"]["per_group"]), ("Vehicle", True))
        # The treated animal alone, before any control that day: refused.
        early = self.read(exp, {drug: {"ct_target": 23, "ct_reference": 18}})
        self.assertEqual(early.status_code, 400)
        self.assertIn("No animal of the control group “Vehicle”", early.get_json()["error"])
        # A whole day at once works whatever the order: the controls go first.
        r = self.read(exp, {drug: {"ct_target": 23, "ct_reference": 18}, v1: {"ct_target": 25, "ct_reference": 18},
                            v2: {"ct_target": 26, "ct_reference": 18}})
        self.assertEqual(r.status_code, 200, r.get_json())
        values = {x["key"]: x["values"][0] for x in r.get_json()["table"]["rows"]}
        self.assertAlmostEqual(values[drug], 2 ** 2.5, places=4)
        self.assertAlmostEqual(values[v1], 2 ** 0.5, places=4)
        stored = one("select value from experiment_readings where experiment_id_fk=? and subject=?", exp, drug)
        self.assertAlmostEqual(stored, 2 ** 2.5, places=4)
        # Another control moves the mean, and the day is worked out again.
        self.read(exp, {v2: {"ct_target": 25, "ct_reference": 18}})
        self.assertAlmostEqual(one("select value from experiment_readings where experiment_id_fk=? and subject=?",
                                   exp, drug), 2 ** 2, places=4)
        # The last control can't go while the others are worked out against it.
        self.read(exp, {v2: {"ct_target": "", "ct_reference": ""}})
        last = self.read(exp, {v1: {"ct_target": "", "ct_reference": ""}})
        self.assertEqual(last.status_code, 400)
        self.assertIn("remove theirs first", last.get_json()["error"])

    def test_a_plain_readout_still_takes_a_number(self):
        exp, keys = self.colony_experiment()
        self.choose(exp, "tumour_volume")
        self.assertEqual(self.read(exp, {keys[0]: "250"}).status_code, 200)
        refused = self.read(exp, {keys[0]: {"length": 12, "width": 8}})
        self.assertIn("typed as one number", refused.get_json()["error"])


class ProposedAndApi(Base):
    def apply(self, *changes):
        out = actions.run(app, self.member, list(changes), apply=True, description=uniq("P"))
        self.assertTrue(out.ok, [c.as_dict() for c in out.changes])
        return out

    def test_experiment_reading_takes_inputs_and_shows_inputs_to_value(self):
        exp, keys = self.colony_experiment()
        self.choose(exp, "derived:tumour_lw")
        label = str(one("select mouse_id from mice where id=?", int(keys[0].split(":")[1])))
        change = {"action": "experiment_reading", "target": {"kind": "experiment", "id": exp},
                  "fields": {"inputs": {label: {"length": 12, "width": 8}}}}
        preview = actions.run(app, self.member, [change])
        self.assertTrue(preview.ok, preview.changes[0].as_dict())
        self.assertIn("Length 12 mm, Width 8 mm → 384 mm³", preview.changes[0].summary)
        self.assertIsNone(one("select value from experiment_readings where experiment_id_fk=?", exp))
        self.apply(change)
        self.assertEqual(one("select value from experiment_readings where experiment_id_fk=? and subject=?", exp, keys[0]),
                         384.0)

    def test_inputs_that_dont_fit_are_refused(self):
        exp, keys = self.colony_experiment()
        self.choose(exp, "derived:tumour_lw")
        label = str(one("select mouse_id from mice where id=?", int(keys[0].split(":")[1])))
        target = {"kind": "experiment", "id": exp}
        out = actions.run(app, self.member, [
            {"action": "experiment_reading", "target": target, "fields": {"values": {label: 384}}},
            {"action": "experiment_reading", "target": target, "fields": {"inputs": {label: {"length": 12}}}},
            {"action": "experiment_reading", "target": target, "fields": {"inputs": {label: {"diameter": 4}}}},
            {"action": "experiment_reading", "target": target, "fields": {}},
        ])
        errors = [" ".join(c.errors) for c in out.changes]
        self.assertIn("send them as inputs", errors[0])
        self.assertIn(f"{label}: Width is missing", errors[1])
        self.assertIn("not diameter", errors[2])
        self.assertIn("needs values", errors[3])
        # A plain readout keeps its plain values, and refuses inputs.
        self.choose(exp, "score")
        out = actions.run(app, self.member, [
            {"action": "experiment_reading", "target": target, "fields": {"values": {label: 2}}},
            {"action": "experiment_reading", "target": target, "fields": {"inputs": {label: {"length": 1, "width": 1}}}}])
        self.assertTrue(out.changes[0].ok, out.changes[0].as_dict())
        self.assertIn("send values, not inputs", " ".join(out.changes[1].errors))

    def test_the_api_records_inputs(self):
        from tests.test_api import Base as ApiBase
        exp, keys = self.colony_experiment()
        self.choose(exp, "derived:delta_ct")
        tok = ApiBase.token(self, self.m)
        r = app.test_client().post(f"/api/v1/experiments/{exp}/readings", headers={"Authorization": f"Bearer {tok}"},
                                   json={"inputs": {keys[0]: {"ct_target": 24, "ct_reference": 18.5}}})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(one("select value from experiment_readings where experiment_id_fk=? and subject=?", exp, keys[0]),
                         5.5)


class TheDeriveTool(Base):
    def setUp(self):
        super().setUp()
        from tests.test_api import Base as ApiBase
        from tests.test_mcp import TestApi, bm
        self.bm = bm
        self.api = TestApi(ApiBase.token(self, self.m, scope="propose"))

    def test_it_lists_and_computes_and_changes_nothing(self):
        listed = self.bm.call_tool(self.api, "derive", {})
        self.assertIn("fold_change", [f["key"] for f in listed["formulas"]])
        out = self.bm.call_tool(self.api, "derive", {"formula": "fold_change", "control": "Vehicle", "rows": [
            {"animal": "1", "group": "Vehicle", "ct_target": 25, "ct_reference": 18},
            {"animal": "2", "group": "Drug", "ct_target": 23, "ct_reference": 18},
            {"animal": "3", "group": "Drug", "ct_target": "Undetermined", "ct_reference": 18}]})
        self.assertEqual(out["rows"][1]["value"], 4.0)
        self.assertIn("never came up", out["rows"][2]["error"])
        self.assertEqual(out["control_mean_delta_ct"], {"all": 7.0})
        refused = self.bm.call_tool(self.api, "derive", {"formula": "fold_change", "rows": [
            {"group": "Drug", "ct_target": 23, "ct_reference": 18}]})
        self.assertIn("which group is the control", refused["error"])
        self.assertIn("not a formula",
                      self.bm.call_tool(self.api, "derive", {"formula": "magic", "rows": [{}]})["error"])

    def test_it_is_a_read_only_tool_everywhere(self):
        from app import assistant_tools, mcp_http
        self.assertIn("derive", assistant_tools.TOOLS)
        self.assertIn("derive", mcp_http.READ_ONLY)
        self.assertEqual(mcp_http.TITLES["derive"], "Derived readout")
        self.assertIn("derived readouts (derive)", assistant_tools.INSTRUCTIONS)
        from pathlib import Path
        local = (Path(__file__).resolve().parent.parent / "mcp" / "biomanager_mcp.py").read_text(encoding="utf-8")
        self.assertIn('@server.tool(name="derive"', local)


if __name__ == "__main__":
    unittest.main()
