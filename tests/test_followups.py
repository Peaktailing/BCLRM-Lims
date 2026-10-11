"""What an end-to-end run of assistants over the MCP tools still found
wanting: a plasmid read without kilobytes of bases (its sequence on
request), with the glycerol stocks that carry it; an amount used in mL of
an item kept in ampoules (its pack size); and a litter's cage, in the reply
and as a filter."""
from __future__ import annotations

import importlib

import sqlalchemy as sa

from tests.base import execute, one, uniq
from tests.test_api import Base
from tests.test_assistant_fixes_propose import errors_of, item_ref, run
from tests.test_inventory import InventoryCase
from tests.test_mcp import TestApi, bm

from app import assistant_tools as tools

SEQUENCE = "ATGACCATGATTACGCCAAGCTTGCATGCCTGCAGGTCGACTCTAGAGGATCCCCGGGTACCGAGCTCGAATTC" * 20


class Plasmids(Base):
    def setUp(self):
        super().setUp()
        self.read = self.token(self.m, scope="read")
        self.plasmid = self.make_plasmid(self.m, uniq("pSeq-"))
        self.number = one("select plasmid_id from plasmids where id=?", self.plasmid)
        self.m.post(f"/plasmids/{self.plasmid}/upload-sequence",
                    data={"sequence_text": f">pSeq\n{SEQUENCE}\n"})

    def get(self, path):
        r = self.call("get", path, self.read)
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True)[:300])
        return r.get_json()

    def test_the_sequence_only_when_asked(self):
        plain = self.get(f"/plasmids/{self.number}")
        for gone in ("sequence", "annotations", "circular"):
            self.assertNotIn(gone, plain)
        self.assertEqual((plain["has_sequence"], plain["length"]), (True, len(SEQUENCE)))
        full = self.get(f"/plasmids/{self.number}?sequence=1")
        self.assertEqual(full["sequence"], SEQUENCE)
        self.assertIn("annotations", full)
        self.assertEqual(self.get(f"/plasmids/{self.number}?sequence=false").get("sequence"), None)
        bad = self.call("get", f"/plasmids/{self.number}?bases=1", self.read)
        self.assertEqual(bad.status_code, 400)
        self.assertIn("sequence", bad.get_json()["error"])
        # The list was always without it, and says how long it is.
        listed = self.get(f"/plasmids?q=pSeq-&limit=1000")["data"]
        mine = next(p for p in listed if p["plasmid_id"] == self.number)
        self.assertEqual(mine["length"], len(SEQUENCE))
        self.assertNotIn("sequence", mine)

    def test_the_get_tool_asks_for_it_in_the_path(self):
        api = TestApi(self.read)
        self.assertNotIn("sequence", bm.get(api, f"plasmids/{self.number}"))
        self.assertEqual(bm.get(api, f"plasmids/{self.number}?sequence=1")["sequence"], SEQUENCE)
        self.assertIn("?sequence=1", tools.TOOLS["get"][0])
        spec = self.get("/openapi.json")["paths"]["/plasmids/{plasmid_id}"]["get"]
        self.assertIn("sequence", [p["name"] for p in spec["parameters"]])

    def test_its_glycerol_stocks(self):
        self.assertEqual(self.get(f"/plasmids/{self.number}")["glycerol_stocks"], [])
        key = InventoryCase.new_module(self.a, "glycerol_stocks")
        box = InventoryCase.make_rack(self.a, key, uniq("Minus 80 "))
        name = uniq("Stbl3 clone ")
        stock = self.make_item(self.m, key, name, attr_plasmid=str(self.number), attr_frozen_on="2026-09-01",
                               rack_id=str(box), position="B3")
        other = self.make_plasmid(self.m, uniq("pOther-"))
        self.make_item(self.m, key, uniq("Not it "),
                       attr_plasmid=str(one("select plasmid_id from plasmids where id=?", other)))
        [entry] = self.get(f"/plasmids/{self.number}")["glycerol_stocks"]
        number = one("select number from inventory_items where id=?", stock)
        self.assertEqual({k: entry[k] for k in ("number", "name", "position", "status", "frozen_on")},
                         {"number": number, "name": name, "position": "B3", "status": "in stock",
                          "frozen_on": "2026-09-01"})
        self.assertEqual(entry["box"], one("select name from inventory_racks where id=?", box))
        self.assertIn(f"/inventory/{key}?open={stock}", entry["url"])


class PackSizes(Base):
    def ampoules(self, pack_size="10 mL", quantity="5") -> int:
        return self.make_item(self.m, "reagents", uniq("Ketamine "), quantity=quantity, unit="ampoules",
                              pack_size=pack_size)

    def test_kept_from_the_sheet_and_dialog_and_refused_when_not_a_size(self):
        item = self.ampoules(pack_size="10mL")
        self.assertEqual(one("select pack_size from inventory_items where id=?", item), "10 mL")
        r = self.autosave(self.m, f"/inventory/reagents/items/{item}/update", {"pack_size": "2,5 mL"})
        self.assertSaved(r)
        self.assertEqual(r.get_json()["row"]["values"]["pack_size"], "2.5 mL")
        r = self.autosave(self.m, f"/inventory/reagents/items/{item}/update", {"pack_size": "a box"})
        self.assertEqual(r.status_code, 409)
        self.assertIn("Pack size is what one of its unit holds", r.get_json()["error"])
        self.assertSaved(self.autosave(self.m, f"/inventory/reagents/items/{item}/update", {"pack_size": ""}))
        self.assertEqual(one("select pack_size from inventory_items where id=?", item), "")
        page = self.get_ok(self.m, "/inventory/reagents")
        self.assertIn('name="pack_size"', page)
        orders = InventoryCase.new_module(self.a, "orders")
        self.assertNotIn('name="pack_size"', self.get_ok(self.a, f"/inventory/{orders}"))

    def test_through_the_api(self):
        tok = self.token(self.m)
        r = self.call("post", "/inventories/reagents/items", tok,
                      json={"name": uniq("Heparin "), "quantity": "4", "unit": "vials", "pack_size": "5 mL"})
        self.assertEqual(r.status_code, 201, r.get_json())
        self.assertEqual(r.get_json()["pack_size"], "5 mL")
        number = r.get_json()["number"]
        r = self.call("patch", f"/inventories/reagents/items/{number}", tok, json={"pack_size": "1 g"})
        self.assertEqual(r.get_json()["pack_size"], "1 g")
        r = self.call("patch", f"/inventories/reagents/items/{number}", tok, json={"pack_size": "lots"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("pack_size", self.call("get", "/actions", tok).get_data(as_text=True))

    def test_an_amount_used_in_ml_comes_off_as_part_of_an_ampoule(self):
        item = self.ampoules()
        out = run(self.member, {"action": "inventory_quantity_used", "target": item_ref(item),
                                "fields": {"amount": "2 mL"}})
        self.assertTrue(out.ok, out.errors)
        self.assertIn("2 mL used, which is 0.2 ampoules (5 → 4.8)", out.changes[0].summary)
        out = run(self.member, {"action": "inventory_quantity_used", "target": item_ref(item),
                                "fields": {"amount": 500, "unit": "µL"}}, apply=True)
        self.assertTrue(out.ok, out.errors)
        self.assertEqual(one("select quantity from inventory_items where id=?", item), "4.95")
        out = run(self.member, {"action": "inventory_quantity_used", "target": item_ref(item),
                                "fields": {"amount": "1 ampoules"}})
        self.assertIn("1 ampoules used (4.95 → 3.95)", out.changes[0].summary)
        out = run(self.member, {"action": "inventory_quantity_used", "target": item_ref(item),
                                "fields": {"amount": "5 mg"}})
        self.assertIn("comes in packs of 10 mL, and 5 mg can't be turned into that", errors_of(out))
        out = run(self.member, {"action": "inventory_quantity_used", "target": item_ref(item),
                                "fields": {"amount": "60 mL"}})
        self.assertIn("Only 4.95 ampoules", errors_of(out))

    def test_without_one_it_says_what_would_do(self):
        item = self.ampoules(pack_size="")
        out = run(self.member, {"action": "inventory_quantity_used", "target": item_ref(item),
                                "fields": {"amount": "2 mL"}})
        self.assertIn("give it a pack size", errors_of(out))
        out = run(self.member, {"action": "inventory_item_change", "target": item_ref(item),
                                "fields": {"pack_size": "10 mL"}}, apply=True)
        self.assertTrue(out.ok, out.errors)
        self.assertEqual(one("select pack_size from inventory_items where id=?", item), "10 mL")
        out = run(self.member, {"action": "inventory_quantity_used", "target": item_ref(item),
                                "fields": {"amount": "2 mL"}})
        self.assertTrue(out.ok, out.errors)

    def test_the_migration_adds_the_column_once(self):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        migration = importlib.import_module("migrations.versions.0036_pack_size")
        engine = sa.create_engine("sqlite://")
        with engine.begin() as conn:
            conn.exec_driver_sql("create table inventory_items (id integer primary key, unit varchar(30))")
            conn.exec_driver_sql("insert into inventory_items (unit) values ('ampoules')")
            for _ in range(2):
                with Operations.context(MigrationContext.configure(conn)):
                    migration.upgrade()
            self.assertEqual(conn.exec_driver_sql("select unit, pack_size from inventory_items").fetchall(),
                             [("ampoules", "")])


class Litters(Base):
    def test_a_litter_names_its_cage_and_is_found_by_it(self):
        tok = self.token(self.m, scope="read")
        birth, weaned = uniq("B"), uniq("W")
        code = uniq("L")
        pups = [self.make_mouse(self.m, self.member, cage=birth, litter=code) for _ in range(3)]
        self.make_mouse(self.m, self.member, cage=weaned, litter=code)
        lonely = uniq("L")
        self.make_litter(self.m, lonely)

        r = self.call("get", f"/litters?cage={birth}", tok)
        self.assertEqual(r.status_code, 200, r.get_json())
        [row] = r.get_json()["data"]
        self.assertEqual((row["litter_id"], row["cage"]), (code, birth))
        self.assertEqual(row["cages"], sorted([birth, weaned]))
        self.assertEqual([x["litter_id"] for x in self.call("get", f"/litters?cage={weaned}", tok).get_json()["data"]],
                         [code])
        every = {x["litter_id"]: x for x in self.call("get", "/litters?limit=1000", tok).get_json()["data"]}
        self.assertEqual((every[lonely]["cage"], every[lonely]["cages"]), (None, []))

        # Its pups gone from the birth cage (dead), it is no longer there.
        for pup in pups:
            execute("update mice set date_of_death=? where id=?", "2026-09-01", pup)
        self.assertEqual(self.call("get", f"/litters?cage={birth}", tok).get_json()["data"], [])
        self.assertEqual(every[code]["cage"], birth)
        r = self.call("get", "/litters?mother=12", tok)
        self.assertEqual(r.status_code, 400)
        self.assertIn("born_since, cage", r.get_json()["error"])
        self.assertIn("litters: born_since, cage", tools.TOOLS["list"][0])
