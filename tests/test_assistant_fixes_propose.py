"""What an end-to-end run of the assistant's tools found on the proposing
side: a corrected proposal replaces one sent back, the reply shows each
record's before → after (and side effects as warnings), stock made from an
order as the lab keeps it, amounts in other units, a litter's pup count,
strains that aren't loci, randomize's groups for a new design, and the
schemas and words assistants read."""
from __future__ import annotations

import json

from tests.base import days_ago, days_ahead, one, row, uniq
from tests.test_api_compute import Compute

from app import actions, assistant_compute as ac
from app.app import app


def run(who, *changes, apply=False):
    return actions.run(app, who, list(changes), apply=apply, description=uniq("P") if apply else "")


def errors_of(out) -> str:
    return " ".join(e for c in out.changes for e in c.errors)


def item_ref(item_id: int) -> dict:
    return {"kind": "inventory_item", "id": item_id}


def litter(cage: int, day: str, **fields) -> dict:
    return {"action": "litter_born", "target": {"kind": "cage", "id": cage}, "fields": {"date": day, **fields}}


class Fixes(Compute):
    def propose(self, *changes, **extra):
        tok = self.token(self.m, scope="propose")
        r = self.call("post", "/proposals", tok, json={"summary": "From my notes", "source": "Claude",
                                                      "changes": list(changes), **extra})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True)[:500])
        return r.get_json()

    # 1. replaces
    def test_a_corrected_proposal_replaces_one_sent_back_invalid_or_waiting(self):
        cage = self.make_cage(self.m)
        sent = self.propose(litter(cage, days_ago(1)))["id"]
        self.post(self.m, f"/proposals/{sent}/send-back", {"reason": "It was two days ago"})
        again = self.propose(litter(cage, days_ago(2)), replaces=sent)
        self.assertEqual((again["status"], again["replaces"]), ("pending", sent))
        self.assertEqual(one("select status from proposals where id=?", sent), "superseded")
        bad = self.propose({"action": "litter_born", "target": {"kind": "cage", "id": 10 ** 9}, "fields": {}})
        self.assertEqual(bad["status"], "invalid")
        fixed = self.propose(litter(cage, days_ago(2)), replaces=bad["id"])
        self.assertEqual(fixed["replaces"], bad["id"])
        self.assertEqual(one("select status from proposals where id=?", bad["id"]), "superseded")
        latest = self.propose(litter(cage, days_ago(3)), replaces=again["id"])
        self.assertEqual(one("select status from proposals where id=?", again["id"]), "superseded")
        # Another person's proposal is neither replaced nor named.
        theirs = self.call("post", "/proposals", self.token(self.o, scope="propose"),
                           json={"summary": "x", "changes": [litter(self.make_cage(self.o), days_ago(1))]}).get_json()
        mine = self.propose(litter(cage, days_ago(1)), replaces=theirs["id"])
        self.assertIsNone(mine["replaces"])
        self.assertEqual(one("select status from proposals where id=?", theirs["id"]), "pending")
        self.assertEqual(one("select status from proposals where id=?", latest["id"]), "pending")

    # 2. records in the reply, and a side effect as a warning
    def test_the_reply_shows_each_records_before_and_after_and_unsharing_warns(self):
        cage = self.make_cage(self.m, purpose="Breeder")
        self.assertEqual(one("select is_shared from mouse_cages where id=?", cage), 1)
        code = one("select cage_id from mouse_cages where id=?", cage)
        body = self.propose({"action": "cage_change", "target": {"kind": "cage", "id": cage},
                             "fields": {"purpose": "Breeding"}})
        change = body["changes"][0]
        fields = [r["changes"]["changes"] for r in change["records"] if r["table"] == "mouse_cages"][0]
        self.assertEqual(fields["is_shared"], [True, False])
        self.assertEqual(fields["purpose"], ["Breeder", "Breeding"])
        self.assertIn(f"Cage {code} will no longer be shared with the lab", " ".join(change["warnings"]))
        self.assertIn("will no longer be shared with the lab", self.get_ok(self.m, "/proposals"))
        self.assertEqual(one("select is_shared from mouse_cages where id=?", cage), 1)    # only previewed
        # Asked for in so many words, it is no surprise: no warning.
        item = self.make_item(self.m, "reagents", is_shared="1")
        out = run(self.member, {"action": "inventory_item_change", "target": item_ref(item),
                                "fields": {"shared": False}})
        self.assertTrue(out.ok, out.errors)
        self.assertEqual(out.changes[0].warnings, [])

    # 3. an order into stock as the lab keeps it
    def test_an_order_stocked_under_its_own_name_quantity_and_unit_with_a_warning_for_a_namesake(self):
        name = uniq("Tamoxifen ")
        existing = self.make_item(self.m, "reagents", name, quantity="1", unit="g")
        order = self.make_item(self.m, "orders", f"{name} 1 g", quantity="1", unit="")
        change = {"action": "order_received", "target": item_ref(order), "fields": {
            "to_stock": "reagents", "name": name, "quantity": "1", "unit": "g", "lot": "L7",
            "expires_on": days_ahead(365), "location_note": "4 °C fridge, door"}}
        out = run(self.member, change)
        self.assertTrue(out.ok, out.errors)
        said = out.changes[0].summary
        self.assertIn(f"added to Reagents: {name}, 1 g, lot L7, expires {days_ahead(365)}", said)
        number = one("select number from inventory_items where id=?", existing)
        self.assertEqual(out.changes[0].warnings,
                         [f"Reagents already has “{name}” (#{number}, 1 g): this adds another item rather than "
                          "adding to it."])
        run(self.member, change, apply=True)
        stock = one("select max(i.id) from inventory_items i join inventory_modules m on m.id=i.module_id_fk "
                    "where m.key='reagents' and i.name=?", name)
        self.assertNotEqual(stock, existing)
        self.assertEqual(row("select quantity, unit, lot, location_note from inventory_items where id=?", stock),
                         ("1", "g", "L7", "4 °C fridge, door"))
        self.assertIn("stocked_as", one("select attrs from inventory_items where id=?", order))
        # Without them, it is the order's, as Add to stock makes it; and they need to_stock.
        plain = self.make_item(self.m, "orders", uniq("Agarose "), quantity="2", unit="bottles")
        out = run(self.member, {"action": "order_received", "target": item_ref(plain), "fields": {"to_stock": "reagents"}})
        self.assertIn(", 2 bottles", out.changes[0].summary)
        self.assertEqual(out.changes[0].warnings, [])
        out = run(self.member, {"action": "order_received", "target": item_ref(plain), "fields": {"name": "x"}})
        self.assertIn("only go with to_stock", errors_of(out))

    # 4. an amount in another unit
    def test_an_amount_used_in_another_unit_is_converted_or_refused_in_words(self):
        item = self.make_item(self.m, "reagents", uniq("Tamoxifen "), quantity="1", unit="g")
        out = run(self.member, {"action": "inventory_quantity_used", "target": item_ref(item),
                                "fields": {"amount": "40 mg"}})
        self.assertTrue(out.ok, out.errors)
        self.assertIn("40 mg used, which is 0.04 g (1 → 0.96)", out.changes[0].summary)
        run(self.member, {"action": "inventory_quantity_used", "target": item_ref(item),
                          "fields": {"amount": 40, "unit": "mg"}}, apply=True)
        self.assertEqual(one("select quantity from inventory_items where id=?", item), "0.96")
        out = run(self.member, {"action": "inventory_quantity_used", "target": item_ref(item),
                                "fields": {"amount": 0.5, "unit": "g"}})
        self.assertIn("0.5 g used (0.96 → 0.46)", out.changes[0].summary)
        out = run(self.member, {"action": "inventory_quantity_used", "target": item_ref(item),
                                "fields": {"amount": "5 µL"}})
        self.assertIn("is kept in g, and 5 µL can't be turned into that", errors_of(out))
        buffer = self.make_item(self.m, "reagents", uniq("PBS "), quantity="0.5", unit="L")
        out = run(self.member, {"action": "inventory_quantity_used", "target": item_ref(buffer),
                                "fields": {"amount": "250 uL"}})
        self.assertIn("which is 0.00025 L (0.5 → 0.49975)", out.changes[0].summary)
        vials = self.make_item(self.m, "reagents", uniq("Taq "), quantity="6", unit="vials")
        out = run(self.member, {"action": "inventory_quantity_used", "target": item_ref(vials),
                                "fields": {"amount": "2 Vials"}})
        self.assertIn("2 vials used (6 → 4)", out.changes[0].summary)
        out = run(self.member, {"action": "inventory_quantity_used", "target": item_ref(vials),
                                "fields": {"amount": 2, "unit": "tubes"}})
        self.assertIn("can't be turned into that", errors_of(out))
        bare = self.make_item(self.m, "reagents", uniq("Beads "), quantity="10")
        out = run(self.member, {"action": "inventory_quantity_used", "target": item_ref(bare),
                                "fields": {"amount": "5 mg"}})
        self.assertIn("has no unit", errors_of(out))
        out = run(self.member, {"action": "inventory_quantity_used", "target": item_ref(bare),
                                "fields": {"amount": "some"}})
        self.assertIn("amount is a number", errors_of(out))

    # 5. a litter's pups
    def test_a_litter_born_with_its_pup_count_and_a_birth_date_it_replaces(self):
        cage = self.make_cage(self.m, purpose="Breeding", notes="pair set up")
        code = one("select cage_id from mouse_cages where id=?", cage)
        out = run(self.member, litter(cage, days_ago(1), pups=8))
        self.assertTrue(out.ok, out.errors)
        self.assertIn(f"Litter of 8 pups born in cage {code}", out.changes[0].summary)
        self.assertEqual(out.changes[0].warnings, [])
        run(self.member, litter(cage, days_ago(1), pups=8), apply=True)
        self.assertEqual(one("select notes from mouse_cages where id=?", cage),
                         f"pair set up; {days_ago(1)}: litter born, 8 pups")
        self.assertEqual(str(one("select date_give_birth from mouse_cages where id=?", cage))[:10], days_ago(1))
        # A second birth while the first litter is still there: the page's own warning, once.
        out = run(self.member, litter(cage, days_ago(0), pups=1))
        self.assertIn("Litter of 1 pup born", out.changes[0].summary)
        replaced = [w for w in out.changes[0].warnings if "replaces the litter born" in w]
        self.assertEqual(len(replaced), 1, out.changes[0].warnings)
        out = run(self.member, litter(cage, days_ago(0), pups=0))
        self.assertIn("pups is a whole number from 1 to 40", errors_of(out))

    # 6. strains aren't loci
    def test_a_strain_wanted_means_both_parents_of_it_never_het_or_wt(self):
        cage = uniq("C")
        self.make_cage(self.m, cage, purpose="Breeder")
        locus = uniq("Fx")
        for sex in ("F", "M"):
            self.make_mouse(self.m, self.member, cage=cage, litter=uniq("L"), date_of_birth=days_ago(70),
                            gender=sex, transgene_1="C57BL/6J")
            self.make_mouse(self.m, self.member, cage=cage, litter=uniq("L"), date_of_birth=days_ago(70),
                            gender=sex, transgene_1="C57BL/6J", transgene_2=f"{locus} fl/+")
        out = self.ok(self.post_json("/breeding-plan", {"want": {"C57BL/6J": "hom"}, "count": 4}))
        self.assertEqual(out["want"], {})
        self.assertEqual(out["strains"], ["C57BL/6J"])
        best = out["crosses"][0]
        self.assertEqual((best["female"], best["male"], best["odds"]), ("C57BL/6J", "C57BL/6J", 1.0))
        self.assertLessEqual(best["matings"], 2)
        self.assertEqual(out["best_possible"][0], {"female": "C57BL/6J", "male": "C57BL/6J", "odds": 1.0})
        self.assertNotIn("C57BL/6J", json.dumps([b["read_as"] for b in out["breeders"]]))
        self.assertIn("breeds true", " ".join(out["assumptions"]))
        both = self.ok(self.post_json("/breeding-plan", {"want": {"C57BL/6J": "hom", locus: "hom"}, "count": 2}))
        best = both["crosses"][0]
        self.assertEqual((best["female"], best["male"], best["odds"]),
                         (f"C57BL/6J; {locus} het", f"C57BL/6J; {locus} het", 0.25))
        r = self.post_json("/breeding-plan", {"want": {"C57BL/6J": "het"}})
        self.assertEqual(r.status_code, 400)
        self.assertIn("is a strain (a background), not an allele or transgene", r.get_json()["error"])
        for name in ("C57BL/6J", "C57BL/6NCrl", "BALB/cJ", "129S6/SvEvTac", "FVB/N", "DBA/2J", "CD-1", "B6"):
            self.assertTrue(ac.is_strain(name, set()), name)
        for name in ("Cre", "Nod2", "Foxp3", "Ai14", "Cd4-Cre", "Rosa26"):
            self.assertFalse(ac.is_strain(name, set()), name)
        self.assertTrue(ac.is_strain("Our Mixed BG", {"our mixed bg"}))

    # 7. randomize for a new design
    def test_randomize_gives_groups_experiment_new_takes_as_they_are_with_the_seed(self):
        mice = [self.make_mouse(self.m, self.member, litter=uniq("L"), date_of_birth=days_ago(60),
                                gender="F" if i % 2 else "M") for i in range(4)]
        out = self.ok(self.post_json("/randomize", {"animals": [self.number(m) for m in mice],
                                                    "groups": ["Vehicle", "Drug"], "seed": 11}))
        self.assertNotIn("propose", out)
        self.assertEqual([g["name"] for g in out["groups"]], ["Vehicle", "Drug"])
        self.assertEqual(sorted(a["id"] for g in out["groups"] for a in g["animals"]), sorted(mice))
        self.assertIn("experiment_new", out["note"])
        name = uniq("Design ")
        change = {"action": "experiment_new", "fields": {"name": name, "groups": out["groups"], "seed": out["seed"]}}
        preview = run(self.member, change)
        self.assertTrue(preview.ok, preview.errors)
        run(self.member, change, apply=True)
        exp, description = row("select id, description from experiments where name=?", name)
        self.assertIn("seed 11", description)
        self.assertEqual(one("select count(*) from experiment_mice where experiment_id_fk=?", exp), 4)

    # 8. experiment_new's schemas
    def test_experiment_new_says_the_shape_of_its_groups_and_steps(self):
        props = actions.CATALOGUE["experiment_new"].schema()["properties"]
        groups, steps = props["groups"], props["steps"]
        self.assertEqual(groups["type"], "array")
        self.assertEqual(set(groups["items"]["properties"]), {"name", "animals", "housing"})
        self.assertEqual(groups["items"]["required"], ["name"])
        self.assertEqual(groups["items"]["properties"]["animals"]["type"], "array")
        self.assertEqual(steps["type"], "array")
        self.assertEqual(set(steps["items"]["properties"]),
                         {"days", "kind", "agent", "dose", "route", "concentration", "group", "notes"})
        self.assertEqual(steps["items"]["required"], ["days"])
        self.assertEqual(props["seed"]["type"], "integer")
        used = actions.CATALOGUE["inventory_quantity_used"].schema()["properties"]
        self.assertEqual(used["amount"]["type"], ["number", "string"])

    # 9. power and Welch's test
    def test_power_says_it_plans_with_one_sd_and_that_welchs_test_is_run(self):
        out = ac.power(2, difference=1, sd=1)
        self.assertIn("same SD", out["test"])
        self.assertIn("Welch's t-test", " ".join(out["assumptions"]))
        self.assertNotIn("Welch", " ".join(ac.power(3, difference=1, sd=1)["assumptions"]))


class BreedingPlanAfterTheSecondRun(Compute):
    """What the second end-to-end run found: a mate carrying another
    transgene counted as suitable, one male for many matings, and a
    planned experiment's mice counted as free."""

    def test_a_mate_carrying_more_comes_after_one_that_doesnt_and_males_can_run_short(self):
        cre, other = uniq("Dat"), uniq("Ai")
        cage = uniq("C")
        self.make_cage(self.m, cage, purpose="Breeder")
        self.make_mouse(self.m, self.member, cage=cage, litter=uniq("L"), date_of_birth=days_ago(70), gender="M",
                        transgene_1=f"{cre}/+")
        self.make_mouse(self.m, self.member, cage=cage, litter=uniq("L"), date_of_birth=days_ago(70), gender="F")
        self.make_mouse(self.m, self.member, cage=cage, litter=uniq("L"), date_of_birth=days_ago(70), gender="F",
                        transgene_1=f"{other}/{other}")
        out = self.ok(self.post_json("/breeding-plan", {"want": {cre: "het"}, "sex": "M", "count": 12}))
        mine = [c for c in out["crosses"] if c["male"].startswith(cre)]
        carries = [c["also_carries"] for c in mine]                    # other tests' breeders may be here too
        self.assertEqual(carries[0], [])
        self.assertIn([f"{other}/{other}"], carries)                   # named, and after the plain cross
        self.assertGreater(mine[0]["males_short"], 0)                  # one male, more matings than two females

    def test_a_planned_experiments_mice_are_taken(self):
        self.assertIn("planned", ac.BUSY)
