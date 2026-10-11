"""What BioManager works out for an assistant (app/assistant_compute.py),
the pure parts: the genotype model, sample sizes, allocation, usage and
the ARRIVE checklist. The endpoints are tests/test_api_compute.py's."""
from __future__ import annotations

import random
import unittest
from datetime import datetime, timedelta

import tests.base  # noqa: F401  (the throwaway database before the app is imported)
from app import assistant_compute as ac
from app import exp_stats


class GenotypeModel(unittest.TestCase):
    def test_one_locus_crosses(self):
        het, hom, wt = {"A": "het"}, {"A": "hom"}, {"A": "wt"}
        self.assertEqual(ac.cross_odds(het, het, {"A": "hom"}), 0.25)
        self.assertEqual(ac.cross_odds(het, het, {"A": "het"}), 0.5)
        self.assertEqual(ac.cross_odds(het, het, {"A": "carrier"}), 0.75)
        self.assertEqual(ac.cross_odds(het, wt, {"A": "het"}), 0.5)
        self.assertEqual(ac.cross_odds(hom, het, {"A": "hom"}), 0.5)
        self.assertEqual(ac.cross_odds(hom, wt, {"A": "het"}), 1.0)
        self.assertEqual(ac.cross_odds(wt, wt, {"A": "hom"}), 0.0)

    def test_cre_and_flox_assort_independently(self):
        # Cre/+; fl/fl × fl/fl: half Cre-positive, all fl/fl.
        mother, father = {"Cre": "het", "fl": "hom"}, {"fl": "hom"}
        self.assertEqual(ac.cross_odds(mother, father, {"Cre": "carrier", "fl": "hom"}), 0.5)
        # Cre/+; fl/+ × fl/+: ½ × ¼.
        self.assertEqual(ac.cross_odds({"Cre": "het", "fl": "het"}, {"fl": "het"}, {"Cre": "carrier", "fl": "hom"}),
                         0.125)
        # Cre-negative littermates of the same cross are the controls: ½ × 1.
        self.assertEqual(ac.cross_odds(mother, father, {"Cre": "wt", "fl": "hom"}), 0.5)

    def test_the_best_crosses_come_first_and_each_pair_once(self):
        best = ac.best_crosses({"A": "hom"})
        self.assertEqual(best[0], {"female": "A hom", "male": "A hom", "odds": 1.0})
        pairs = [tuple(sorted((b["female"], b["male"]))) for b in best]
        self.assertEqual(len(pairs), len(set(pairs)))
        self.assertEqual([b["odds"] for b in best], sorted((b["odds"] for b in best), reverse=True))
        self.assertIn({"female": "A het", "male": "A het", "odds": 0.25}, best)

    def test_the_ways_people_say_a_genotype(self):
        self.assertEqual(ac.state("Heterozygous"), "het")
        self.assertEqual(ac.state("+/+"), "wt")
        self.assertEqual(ac.state("-/-"), "hom")
        self.assertEqual(ac.state("positive", wanted=True), "carrier")
        with self.assertRaises(ValueError):
            ac.state("carrier")                     # a parent is het or hom, not "a carrier"
        with self.assertRaises(ValueError):
            ac.state("purple", wanted=True)

    def test_reading_what_the_lab_wrote(self):
        read = ac.read_locus
        self.assertEqual(read("Foxp3 fl/fl; DBH-Cre", "Foxp3"), ("hom", True))
        self.assertEqual(read("Foxp3 fl/+", "Foxp3"), ("het", True))
        self.assertEqual(read("Foxp3 +/+", "Foxp3"), ("wt", True))
        self.assertEqual(read("Foxp3 fl/fl; DBH-Cre", "Cre"), ("het", False))     # a transgene with no count
        self.assertEqual(read("Cre+/-", "Cre"), ("het", True))
        self.assertEqual(read("Cre/Cre", "Cre"), ("hom", True))
        self.assertEqual(read("Cre-", "Cre"), ("wt", True))
        self.assertEqual(read("Ai14/+", "Ai14"), ("het", True))
        self.assertEqual(read("Gad2 KO -/-", "Gad2 KO"), ("hom", True))
        self.assertEqual(read("Ai14", "Cre"), ("wt", False))                      # not written: wild type
        self.assertEqual(read("het", "Gad2", only_locus=True), ("het", False))     # a bare state, one locus
        self.assertEqual(read("het", "Gad2"), ("wt", False))
        self.assertEqual(read("Cre+/-", "Gad2", only_locus=True), ("wt", False))  # another gene's state


class EnoughPups(unittest.TestCase):
    def test_binomial_tail(self):
        self.assertAlmostEqual(ac.binomial_at_least(2, 0.5, 1), 0.75)
        self.assertAlmostEqual(ac.binomial_at_least(10, 0.3, 0), 1.0)
        self.assertEqual(ac.binomial_at_least(3, 0.5, 4), 0.0)
        self.assertAlmostEqual(ac.binomial_at_least(4, 0.5, 4), 1 / 16)

    def test_matings_on_average_and_to_be_sure(self):
        need = ac.matings_needed(10, 0.25, 6)
        self.assertEqual(need["expected"], 7)            # 1.5 a litter
        self.assertGreater(need["sure"], need["expected"])
        self.assertEqual(ac.matings_needed(1, 1.0, 6), {"expected": 1, "sure": 1, "wanted_per_litter": 6})
        self.assertEqual(ac.matings_needed(5, 0.0, 6)["sure"], None)


class Power(unittest.TestCase):
    """Against G*Power's exact answers."""

    def test_two_groups(self):
        for d, n in ((0.2, 394), (0.5, 64), (0.8, 26), (1.0, 17)):
            self.assertEqual(ac.power(d=d)["n_per_group"], n, d)
        out = ac.power(difference=5, sd=10)
        self.assertEqual((out["n_per_group"], out["total"], out["effect"]["cohens_d"]), (64, 128, 0.5))
        self.assertGreaterEqual(out["achieved_power"], 0.8)
        self.assertIn("t-test", out["test"])
        self.assertEqual(ac.power(d=1.0, alpha=0.01, target=0.9)["n_per_group"], 32)

    def test_more_groups(self):
        self.assertEqual(ac.n_per_group(3, 0.25 ** 2 * 3)["n"], 53)          # Cohen's f 0.25
        self.assertEqual(ac.n_per_group(4, 0.4 ** 2 * 4)["n"], 19)
        # Means 0, 0.5 and 1 spread as much as 0 and 1 with the third midway.
        by_means = ac.power(k=3, sd=1, means=[0, 0.5, 1])
        self.assertIn("ANOVA", by_means["test"])
        least = ac.power(k=3, difference=1, sd=1)
        self.assertEqual(least["n_per_group"], by_means["n_per_group"])
        self.assertEqual(least["n_per_group"], ac.n_per_group(3, 0.5)["n"])
        self.assertTrue(any("least favourable" in a for a in least["assumptions"]))

    def test_losses_and_refusals(self):
        out = ac.power(d=0.5, attrition=0.2)
        self.assertEqual((out["n_per_group"], out["enrol_per_group"]), (64, 80))
        for bad in ({"k": 1, "d": 1}, {"d": 0}, {"sd": 0, "difference": 1}, {"difference": 1},
                    {"d": 1, "alpha": 0.7}, {"k": 3, "sd": 1, "means": [1, 2]}):
            with self.assertRaises(ValueError, msg=bad):
                ac.power(**bad)

    def test_noncentral_f_is_the_central_one_without_an_effect(self):
        for f in (0.5, 1.0, 3.0):
            self.assertAlmostEqual(ac.noncentral_f_cdf(f, 2, 20, 0), 1 - exp_stats.f_upper(f, 2, 20), places=10)
        self.assertLess(ac.noncentral_f_cdf(3.0, 2, 20, 10), ac.noncentral_f_cdf(3.0, 2, 20, 0))
        self.assertAlmostEqual(exp_stats.f_upper(ac.f_critical(0.05, 1, 30), 1, 30), 0.05, places=6)

    def test_pooled_sd(self):
        sd, df = ac.pooled_sd([[1, 2, 3], [4, 5, 6], [9]])
        self.assertAlmostEqual(sd, 1.0)
        self.assertEqual(df, 4)
        self.assertEqual(ac.pooled_sd([[1], [2]]), (None, 0))


class Allocation(unittest.TestCase):
    def animals(self, n=12):
        rng = random.Random(1)
        return [{"key": i, "sex": "F" if i % 2 else "M", "stratum": f"L{i % 3}",
                 "weight": round(20 + rng.random() * 6, 1)} for i in range(n)]

    def test_the_same_seed_gives_the_same_groups(self):
        groups = [{"name": "Vehicle", "size": 6}, {"name": "Drug", "size": 6}]
        first = ac.allocate(self.animals(), groups, 42)
        again = ac.allocate(self.animals(), groups, 42)
        self.assertEqual([[a["key"] for a in g["animals"]] for g in first["groups"]],
                         [[a["key"] for a in g["animals"]] for g in again["groups"]])
        others = {tuple(sorted(a["key"] for a in ac.allocate(self.animals(), groups, s)["groups"][0]["animals"]))
                  for s in range(20)}
        self.assertGreater(len(others), 1)              # the seed decides

    def test_balanced_by_size_sex_stratum_and_weight(self):
        out = ac.allocate(self.animals(), [{"name": "A", "size": 6}, {"name": "B", "size": 6}], 7)
        for g in out["groups"]:
            self.assertEqual(len(g["animals"]), 6)
            self.assertEqual(sum(1 for a in g["animals"] if a["sex"] == "F"), 3)
            for s in ("L0", "L1", "L2"):
                self.assertEqual(sum(1 for a in g["animals"] if a["stratum"] == s), 2)
        table = ac.balance(out["groups"])
        self.assertLess(table["weight_difference"], 1.5)
        for seed in range(30):                           # whatever the seed
            groups = ac.allocate(self.animals(), [{"name": "A", "size": 6}, {"name": "B", "size": 6}], seed)["groups"]
            self.assertEqual([sum(1 for a in g["animals"] if a["sex"] == "F") for g in groups], [3, 3], seed)
        self.assertEqual([g["sex"] for g in table["groups"]], [{"F": 3, "M": 3}] * 2)
        self.assertIn(table["weight_test"]["test"], ("Welch's t-test", "One-way ANOVA"))

    def test_unequal_sizes_and_spares(self):
        out = ac.allocate(self.animals(10), [{"name": "A", "size": 3}, {"name": "B", "size": 5}], 3)
        self.assertEqual([len(g["animals"]) for g in out["groups"]], [3, 5])
        self.assertEqual(len(out["spares"]), 2)
        with self.assertRaises(ValueError):
            ac.allocate(self.animals(4), [{"name": "A", "size": 3}, {"name": "B", "size": 3}], 3)
        sizes = ac.split_sizes(10, ["A", "B", "C"], random.Random(5))
        self.assertEqual((sum(sizes), sorted(sizes)), (10, [3, 3, 4]))


class Usage(unittest.TestCase):
    def test_use_is_the_falls_over_the_days_watched(self):
        now = datetime(2026, 10, 11)
        since = now - timedelta(days=20)
        changes = [(now - timedelta(days=15), 10, 8), (now - timedelta(days=10), 8, 20),   # a restock
                   (now - timedelta(days=5), 20, 16)]
        rate = ac.usage_rate(changes, since, now)
        self.assertEqual((rate["used"], rate["falls"], rate["days"]), (6, 2, 20.0))
        self.assertAlmostEqual(rate["per_day"], 0.3)
        self.assertIsNone(ac.usage_rate([(now, 10, 12)], since, now))                     # only restocked
        self.assertIsNone(ac.usage_rate(changes, now - timedelta(days=3), now))           # under a week


class Interval(unittest.TestCase):
    def test_t_quantile_and_a_difference(self):
        self.assertAlmostEqual(ac.t_quantile(0.05, 1e6), 1.96, places=2)
        self.assertAlmostEqual(ac.t_quantile(0.05, 10), 2.228, places=3)
        out = ac.difference_ci([10, 12, 14], [4, 6, 8])
        self.assertEqual(out["difference"], 6)
        self.assertAlmostEqual(sum(out["ci"]) / 2, 6)
        self.assertLess(out["ci"][0], 6)


class Arrive(unittest.TestCase):
    def facts(self, text=""):
        return {"text": text,
                "animals": {"species": "Mus musculus (mouse)", "total": 8, "ended": 1, "sex": {"F": 8},
                            "genotypes": {"C57BL/6J": 8},
                            "groups": [{"group": "Vehicle", "n": 4}, {"group": "Tamoxifen", "n": 4}],
                            "age_at_start_days": {"min": 56, "max": 63, "median": 60, "mean": 60, "n": 8},
                            "weight_at_start_g": None},
                "procedures": [{"what": "Tamoxifen 75 mg/kg i.p.", "days": "1–5", "group": "Tamoxifen", "done": 5,
                                "lots": ["Tamoxifen lot T123"]}],
                "readouts": {"label": "Body weight", "unit": "g", "days_measured": 4, "first": "2026-09-01",
                             "last": "2026-09-20"},
                "statistics": {"tests": ["Welch's t-test"], "last_day": None}}

    def test_ten_items_with_what_is_recorded_and_missing(self):
        items = ac.arrive(self.facts())
        self.assertEqual([i["item"] for i in items], list(range(1, 11)))
        self.assertEqual(items[0]["name"], "Study design")
        by = {i["name"]: i for i in items}
        self.assertIn("Control group: Vehicle.", by["Study design"]["recorded"])
        self.assertEqual(by["Randomisation"]["status"], "missing")
        self.assertEqual(by["Blinding"]["status"], "missing")
        self.assertIn("Tamoxifen lot T123", " ".join(by["Experimental procedures"]["recorded"]))
        self.assertIn("1 animal(s) died", by["Inclusion and exclusion criteria"]["recorded"][0])
        self.assertTrue(any("56–63 days" in r for r in by["Experimental animals"]["recorded"]))
        self.assertEqual(by["Results"]["status"], "missing")

    def test_what_the_experiment_says_counts(self):
        items = {i["name"]: i for i in ac.arrive(self.facts(
            "Mice were randomised by cage. The scorer was blinded to group. n from a power calculation."))}
        self.assertEqual(items["Randomisation"]["status"], "recorded")
        self.assertIn("randomised", items["Randomisation"]["recorded"][0])
        self.assertEqual(items["Blinding"]["status"], "recorded")
        self.assertEqual(items["Sample size"]["status"], "recorded")


if __name__ == "__main__":
    unittest.main()
