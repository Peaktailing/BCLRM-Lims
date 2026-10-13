"""An experiment's other measures beside its main readout (app/experiments.py):
renamed (its readings stay) or deleted with its readings, as one batch Batch
history's Undo brings back; recorded in bench mode; and a measure BioManager
works out from two genes' Cts (ΔCt, ΔΔCt, fold change), filled from a qPCR
plate or typed on the sheet, in Export and in experiment_summary."""
from __future__ import annotations

import io
import json
import unittest
from datetime import date, timedelta

from tests.base import *  # noqa: F401,F403
from tests.base import count, one, rows
from tests.test_plate_layouts import GRID, QPCR, Base

from app import actions
from app.app import app

TODAY = date.today()
YESTERDAY = (TODAY - timedelta(days=1)).isoformat()


def readout_json(exp) -> dict:
    return json.loads(one("select readout from experiments where id=?", exp))


class MeasureBase(Base):
    def with_measure(self, label="IL-6 ELISA", unit="pg/mL", **kw):
        """A tumour experiment with another measure a plate filled (three readings yesterday)."""
        exp, keys = self.experiment(readout={"readout": "tumour_volume"}, **kw)
        layout = self.save_layout(exp, self.grid_layout(keys)).get_json()["id"]
        r = self.m.post(f"/experiments/{exp}/plates/save", data={"layout_id": layout, "text": GRID, "on": YESTERDAY,
                                                                 "measure": "new", "measure_label": label,
                                                                 "measure_unit": unit})
        self.assertEqual(r.status_code, 200, r.get_json())
        return exp, keys

    def qpcr_layout(self, exp, keys):
        wells = {}
        for row, key in zip("ABC", keys):
            for col in range(1, 5):
                wells[f"{row}{col}"] = key
        return self.save_layout(exp, wells, name="qPCR").get_json()["id"]


class RenamingAMeasure(MeasureBase):
    def test_renaming_keeps_its_id_and_its_readings(self):
        exp, keys = self.with_measure()
        r = self.m.post(f"/experiments/{exp}/measures/1/update", json={"label": "Serum IL-6", "unit": "ng/mL"})
        self.assertEqual(r.status_code, 200, r.get_json())
        measure = r.get_json()["measures"][0]
        self.assertEqual((measure["key"], measure["label"], measure["unit"], measure["count"]),
                         ("measure:1", "Serum IL-6", "ng/mL", 3))
        self.assertEqual(next(x for x in measure["table"]["rows"] if x["key"] == keys[0])["values"], [0.45])
        self.assertEqual(count("experiment_readings", "experiment_id_fk=? and readout_key='measure:1'", exp), 3)
        # Found by its new name, by an assistant's change as by the page.
        self.m.post(f"/experiments/{exp}/readings", json={"on": TODAY.isoformat(), "values": {keys[0]: "0.7"},
                                                           "measure": "serum il-6"})
        self.assertEqual(count("experiment_readings", "experiment_id_fk=? and readout_key='measure:1'", exp), 4)

    def test_a_name_it_cant_have_is_refused_in_words(self):
        exp, _keys = self.with_measure()
        layout = one("select max(id) from plate_layouts where experiment_id_fk=?", exp)
        self.m.post(f"/experiments/{exp}/plates/save", data={"layout_id": layout, "text": GRID, "measure": "new",
                                                             "measure_label": "TNF ELISA"})
        clash = self.m.post(f"/experiments/{exp}/measures/1/update", json={"label": "tnf elisa"})
        self.assertEqual(clash.status_code, 409)
        self.assertIn("already has a measure", clash.get_json()["error"])
        main = self.m.post(f"/experiments/{exp}/measures/1/update", json={"label": "Tumour volume"})
        self.assertIn("main readout", main.get_json()["error"])
        blank = self.m.post(f"/experiments/{exp}/measures/1/update", json={"label": "  "})
        self.assertIn("Name the measure", blank.get_json()["error"])
        self.assertEqual(self.m.post(f"/experiments/{exp}/measures/9/update", json={"label": "x"}).status_code, 404)
        self.assertEqual([m["label"] for m in readout_json(exp)["measures"]], ["IL-6 ELISA", "TNF ELISA"])

    def test_only_who_may_edit_the_experiment_renames_or_deletes(self):
        exp, _keys = self.with_measure()
        r = self.o.post(f"/experiments/{exp}/measures/1/update", json={"label": "Mine"})
        self.assertEqual(r.status_code, 403)
        self.assertTrue(r.get_json()["error"])
        r = self.o.post(f"/experiments/{exp}/measures/1/delete")
        self.assertEqual(r.status_code, 403)
        self.assertTrue(r.get_json()["error"])
        self.assertEqual(readout_json(exp)["measures"][0]["label"], "IL-6 ELISA")
        self.assertEqual(count("experiment_readings", "experiment_id_fk=? and readout_key='measure:1'", exp), 3)
        # The page offers the ••• to who may edit only (it's drawn from editable).
        self.assertIn('id="xp-measure"', self.get_ok(self.m, f"/colony/experiments/{exp}"))
        self.assertNotIn('id="xp-measure"', self.get_ok(self.o, f"/colony/experiments/{exp}"))


class DeletingAMeasure(MeasureBase):
    def test_delete_takes_its_readings_and_undo_brings_both_back(self):
        exp, keys = self.with_measure()
        self.m.post(f"/experiments/{exp}/readings", json={"on": YESTERDAY, "values": {keys[0]: "12"}})   # the main readout
        r = self.m.post(f"/experiments/{exp}/measures/1/delete")
        self.assertEqual(r.status_code, 200, r.get_json())
        out = r.get_json()
        self.assertIn("3 readings", out["message"])
        self.assertEqual(out["measures"], [])
        self.assertEqual(count("experiment_readings", "experiment_id_fk=? and readout_key='measure:1'", exp), 0)
        self.assertEqual(count("experiment_readings", "experiment_id_fk=? and readout_key='tumour_volume'", exp), 1)
        self.assertEqual(readout_json(exp)["key"], "tumour_volume")
        self.assertEqual(readout_json(exp)["measures"], [])
        batch, description = rows("select id, description from batches where actor=? order by id desc", self.member)[0]
        self.assertIn("IL-6 ELISA", description)
        self.assertEqual(count("audit_log", "batch_id_fk=? and table_name='experiment_readings'", batch), 3)
        self.assertEqual(count("audit_log", "batch_id_fk=? and table_name='experiments'", batch), 1)
        self.post(self.m, f"/batches/{batch}/undo")
        self.assertEqual([m["label"] for m in readout_json(exp)["measures"]], ["IL-6 ELISA"])
        got = dict(rows("select subject, value from experiment_readings where experiment_id_fk=? "
                        "and readout_key='measure:1'", exp))
        self.assertEqual(got, {keys[0]: 0.45, keys[1]: 0.6525, keys[2]: 0.855})
        page = self.m.get(f"/experiments/{exp}/data.json").get_json()
        self.assertEqual((page["measures"][0]["label"], page["measures"][0]["count"]), ("IL-6 ELISA", 3))

    def test_a_deleted_measure_s_number_is_not_given_again(self):
        exp, keys = self.with_measure()
        self.m.post(f"/experiments/{exp}/measures/1/delete")
        layout = one("select max(id) from plate_layouts where experiment_id_fk=?", exp)
        saved = self.m.post(f"/experiments/{exp}/plates/save", data={"layout_id": layout, "text": GRID, "measure": "new",
                                                                     "measure_label": "IL-10 ELISA"}).get_json()
        self.assertEqual(saved["filled"], "measure:2")
        # Changing the main readout keeps both the measures and that count.
        self.m.post(f"/experiments/{exp}/update", data={"readout": "body_weight"}, headers={"X-Autosave": "1"})
        self.assertEqual((readout_json(exp)["last_measure"], [m["id"] for m in readout_json(exp)["measures"]]), (2, [2]))


class AtTheBench(MeasureBase):
    def test_bench_mode_has_each_measure_to_record_into(self):
        exp, keys = self.with_measure()
        page = self.get_ok(self.m, f"/experiments/{exp}/bench")
        data = json.loads(page.split('id="xb-data">', 1)[1].split("</script>", 1)[0])
        self.assertEqual([(m["key"], m["label"]) for m in data["measures"]], [("measure:1", "IL-6 ELISA")])
        # What the bench posts for one animal: the sheet's route, the measure's key.
        r = self.m.post(f"/experiments/{exp}/readings", json={"on": TODAY.isoformat(), "values": {keys[1]: "0.9"},
                                                               "measure": "measure:1"})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(one("select value from experiment_readings where subject=? and readout_key='measure:1' "
                             "and read_on=?", keys[1], TODAY.isoformat()), 0.9)
        self.assertEqual(count("experiment_readings", "experiment_id_fk=? and readout_key='tumour_volume'", exp), 0)
        bad = self.m.post(f"/experiments/{exp}/readings", json={"on": TODAY.isoformat(), "values": {keys[1]: "-1"},
                                                                 "measure": "measure:1"})
        self.assertIn("below zero", bad.get_json()["error"])
        self.assertIn("experiment-bench.js", page)


class ACtMeasure(MeasureBase):
    def test_a_delta_ct_measure_filled_from_a_qpcr_plate(self):
        exp, keys = self.experiment(readout={"readout": "tumour_volume"})
        layout = self.qpcr_layout(exp, keys)
        form = {"layout_id": layout, "text": QPCR, "measure": "new", "measure_label": "Il6 ΔCt",
                "measure_kind": "delta_ct", "target": "Il6", "reference": "Gapdh", "on": YESTERDAY}
        preview = self.m.post(f"/experiments/{exp}/plates/preview", data=form).get_json()
        self.assertEqual((preview["mode"], preview["target"], preview["reference"]), ("ct", "Il6", "Gapdh"))
        self.assertNotIn("measures", readout_json(exp))
        saved = self.m.post(f"/experiments/{exp}/plates/save", data=form).get_json()
        self.assertEqual((saved["saved"], saved["filled"]), (3, "measure:1"), saved)
        self.assertEqual(readout_json(exp)["measures"][0], {"id": 1, "label": "Il6 ΔCt", "unit": "", "formula": "delta_ct"})
        got = dict(rows("select subject, value from experiment_readings where readout_key='measure:1' "
                        "and experiment_id_fk=?", exp))
        self.assertEqual(got, {keys[0]: 6.95, keys[1]: 6.0, keys[2]: 5.0})
        note = one("select note from experiment_readings where experiment_id_fk=? and subject=?", exp, keys[0])
        self.assertEqual(json.loads(note), {"ct_target": 25.1, "ct_reference": 18.15})
        measure = saved["measures"][0]
        self.assertEqual((measure["formula"], measure["expression"]), ("delta_ct", "Ct target − Ct reference"))
        # The plate dialog lists it with its kind, so the next plate asks for the genes again.
        listed = self.m.get(f"/experiments/{exp}/plates.json").get_json()["others"]
        self.assertEqual(listed[0]["formula"], "delta_ct")
        # A new measure of that name but another kind is refused.
        clash = self.m.post(f"/experiments/{exp}/plates/preview", data={**form, "measure_kind": ""})
        self.assertIn("of another kind", clash.get_json()["error"])

    def test_typed_on_the_sheet_as_two_cts_or_as_the_delta_ct(self):
        exp, keys = self.experiment(readout={"readout": "tumour_volume"})
        layout = self.qpcr_layout(exp, keys)
        self.m.post(f"/experiments/{exp}/plates/save", data={"layout_id": layout, "text": QPCR, "measure": "new",
                                                             "measure_label": "Il6 ΔCt", "measure_kind": "delta_ct",
                                                             "target": "Il6", "reference": "Gapdh", "on": YESTERDAY})
        on = TODAY.isoformat()
        r = self.m.post(f"/experiments/{exp}/readings", json={"on": on, "measure": "measure:1",
                                                               "values": {keys[0]: "24.8 − 18.2", keys[1]: "-1.5",
                                                                          keys[2]: "25,5 18,5"}})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["problems"], [])
        got = {k: (v, n) for k, v, n in rows("select subject, value, note from experiment_readings where "
                                             "readout_key='measure:1' and read_on=? and experiment_id_fk=?", on, exp)}
        self.assertEqual(got[keys[0]], (6.6, json.dumps({"ct_target": 24.8, "ct_reference": 18.2})))
        self.assertEqual(got[keys[1]], (-1.5, ""))
        self.assertEqual(got[keys[2]][0], 7.0)
        table = r.get_json()["measures"][0]["table"]
        row = next(x for x in table["rows"] if x["key"] == keys[0])
        self.assertEqual(row["inputs"][1], {"ct_target": 24.8, "ct_reference": 18.2})
        for typed, words in (("abc", "Type the two Cts"), ("60 - 20", "isn't one a run gives"), ("75", "ΔCt of 75")):
            bad = self.m.post(f"/experiments/{exp}/readings", json={"on": on, "measure": "measure:1",
                                                                     "values": {keys[0]: typed}})
            self.assertEqual(bad.status_code, 400, typed)
            self.assertIn(words, bad.get_json()["error"])
        # The main readout keeps taking one number.
        self.m.post(f"/experiments/{exp}/readings", json={"on": on, "values": {keys[0]: "120"}})
        self.assertEqual(one("select value from experiment_readings where readout_key='tumour_volume' and subject=?",
                             keys[0]), 120)

    def test_a_fold_change_measure_against_the_control_group(self):
        exp, keys = self.experiment(groups=("Vehicle", "Drug", "Drug"), readout={"readout": "tumour_volume"})
        layout = self.qpcr_layout(exp, keys)
        form = {"layout_id": layout, "text": QPCR, "measure": "new", "measure_label": "Il6 fold change",
                "measure_kind": "fold_change", "target": "Il6", "reference": "Gapdh", "on": YESTERDAY}
        refused = self.m.post(f"/experiments/{exp}/plates/preview", data=form).get_json()
        self.assertTrue(any("control of Il6 fold change" in (s.get("error") or "") for s in refused.get("subjects", []))
                        or "control of Il6 fold change" in (refused.get("error") or ""), refused)
        saved = self.m.post(f"/experiments/{exp}/plates/save", data={**form, "measure_control": "Vehicle"}).get_json()
        self.assertEqual(saved["saved"], 3, saved)
        values = dict(rows("select subject, value from experiment_readings where readout_key='measure:1' "
                           "and experiment_id_fk=?", exp))
        self.assertEqual(values[keys[0]], 1.0)
        self.assertAlmostEqual(values[keys[1]], 2 ** 0.95, places=3)
        # Typed: two Cts, never the fold change itself.
        on = TODAY.isoformat()
        bad = self.m.post(f"/experiments/{exp}/readings", json={"on": on, "measure": "measure:1",
                                                                 "values": {keys[0]: "1.2"}})
        self.assertIn("Type the two Cts", bad.get_json()["error"])
        ok = self.m.post(f"/experiments/{exp}/readings", json={"on": on, "measure": "measure:1",
                                                                "values": {keys[1]: "25 - 18", keys[0]: "26 - 18"}})
        self.assertEqual(ok.status_code, 200, ok.get_json())
        self.assertEqual(one("select value from experiment_readings where readout_key='measure:1' and subject=? "
                             "and read_on=?", keys[1], on), 2.0)
        # A new control group: each day is worked out against it.
        r = self.m.post(f"/experiments/{exp}/measures/1/update", json={"control": "Drug"})
        self.assertEqual(r.json["measures"][0]["control"], "Drug")
        self.assertEqual(one("select value from experiment_readings where readout_key='measure:1' and subject=? "
                             "and read_on=?", keys[1], on), 1.0)
        # Its unit isn't one to give: the Cts make it.
        self.m.post(f"/experiments/{exp}/measures/1/update", json={"unit": "pg"})
        self.assertEqual(readout_json(exp)["measures"][0]["unit"], "")

    def test_export_and_the_summary_show_it(self):
        exp, keys = self.experiment(readout={"readout": "tumour_volume"})
        layout = self.qpcr_layout(exp, keys)
        self.m.post(f"/experiments/{exp}/plates/save", data={"layout_id": layout, "text": QPCR, "measure": "new",
                                                             "measure_label": "Il6 ΔCt", "measure_kind": "delta_ct",
                                                             "target": "Il6", "reference": "Gapdh"})
        r = self.m.get(f"/experiments/{exp}/export.xlsx")
        from openpyxl import load_workbook
        book = load_workbook(io.BytesIO(r.data))
        sheet = list(book["Il6 ΔCt"].values)
        self.assertIn("Il6 ΔCt", sheet[0])
        self.assertIn("Ct of the target gene", sheet[0])
        self.assertEqual(len(sheet), 4)
        from app.assistant_compute import experiment_summary
        from app.db import SessionLocal
        with app.test_request_context("/"), SessionLocal() as s:
            summary = experiment_summary(s, exp)
        other = summary["readouts"]["other_measures"][0]
        self.assertEqual((other["label"], other["formula"], other["days_measured"]), ("Il6 ΔCt", "delta_ct", 1))
        outcome = next(i for i in summary["arrive"] if i["item"] == 6)
        self.assertTrue(any("Il6 ΔCt, Ct target − Ct reference" in r for r in outcome["recorded"]))

    def test_an_assistant_records_it_as_inputs(self):
        exp, keys = self.experiment(readout={"readout": "tumour_volume"})
        layout = self.qpcr_layout(exp, keys)
        self.m.post(f"/experiments/{exp}/plates/save", data={"layout_id": layout, "text": QPCR, "measure": "new",
                                                             "measure_label": "Il6 ΔCt", "measure_kind": "delta_ct",
                                                             "target": "Il6", "reference": "Gapdh"})
        change = {"action": "experiment_reading", "target": {"kind": "experiment", "id": exp},
                  "fields": {"measure": "Il6 ΔCt", "date": YESTERDAY,
                             "inputs": {keys[0]: {"ct_target": 26, "ct_reference": 18}}}}
        out = actions.run(app, self.member, [change])
        self.assertTrue(out.ok, out.changes[0].as_dict())
        self.assertIn("→ 8", out.changes[0].as_dict()["summary"])


class ForAnAssistant(MeasureBase):
    def change(self, exp, **fields):
        return {"action": "experiment_measure_change", "target": {"kind": "experiment", "id": exp}, "fields": fields}

    def test_rename_and_delete_as_changes_to_propose(self):
        exp, _keys = self.with_measure()
        preview = actions.run(app, self.member, [self.change(exp, measure="IL-6 ELISA", label="Serum IL-6")])
        self.assertTrue(preview.ok, preview.changes[0].as_dict())
        self.assertIn("label → Serum IL-6", preview.changes[0].as_dict()["summary"])
        self.assertEqual(readout_json(exp)["measures"][0]["label"], "IL-6 ELISA")      # a preview changes nothing
        done = actions.run(app, self.member, [self.change(exp, measure="measure:1", label="Serum IL-6")], apply=True,
                           description="rename")
        self.assertTrue(done.ok, done.changes[0].as_dict())
        self.assertEqual(readout_json(exp)["measures"][0]["label"], "Serum IL-6")
        said = actions.run(app, self.member, [self.change(exp, measure="Serum IL-6", delete=True)])
        self.assertIn("with its 3 readings", said.changes[0].as_dict()["summary"])
        gone = actions.run(app, self.member, [self.change(exp, measure="Serum IL-6", delete=True)], apply=True,
                           description="delete")
        self.assertTrue(gone.ok, gone.changes[0].as_dict())
        self.assertEqual(count("experiment_readings", "experiment_id_fk=? and readout_key='measure:1'", exp), 0)
        unknown = actions.run(app, self.member, [self.change(exp, measure="IFN", label="x")])
        self.assertIn("no measure", unknown.changes[0].as_dict()["errors"][0])
        refused = actions.run(app, self.other, [self.change(exp, measure="IFN", label="x")])
        self.assertFalse(refused.ok)


if __name__ == "__main__":
    unittest.main()
