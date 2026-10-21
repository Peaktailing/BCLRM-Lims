"""The teaching loop's top: courses (app/chemical_courses.py and the
course routes in app/chemical_experiments_routes.py).

A course holds the templates; each student starts a copy of one, weighs
at the bench, and the term's usage is read back per substance. The
worked example is again the aspirin class: one template, two students'
copies with different weighings, and the usage table that adds them up.
"""
from __future__ import annotations

# tests.base first: it points the app at a throwaway database before app is imported.
from tests.base import *  # noqa: F401,F403
from tests.base import one, row
from tests import test_chemical_experiments as chem_tests
from tests import test_inventory as inv_tests

from app import chemical_courses as course_plans
from app.models import ChemicalExperiment


class CourseCase(chem_tests.ChemicalExperimentCase):
    """The aspirin class's fixtures (the anhydride's bottle, the module)
    plus the course helpers."""

    def make_course(self, name: str | None = None, **extra) -> int:
        data = {"name": name or "有机化学实验", "term": "2026-2027-1",
                "teacher": "王老师", "student_count": 30}
        data.update(extra)
        r = self.a.post("/chem-experiments/courses", data=data)
        self.assertEqual(r.status_code, 302)
        return one("select max(id) from experiment_courses where name=?", data["name"])

    def make_template(self, course_id: int, title: str = "阿司匹林合成") -> int:
        """A template plan of the aspirin class, belonging to the course."""
        data = {"title": title, "kind": "synthesis", "course_id": str(course_id),
                "reaction": chem_tests.REACTION, "reagents": chem_tests.REAGENTS,
                "weighed": chem_tests.WEIGHED, "product_cas": chem_tests.ASPIRIN,
                "status": "template"}
        r = self.a.post("/chem-experiments", data=data)
        self.assertEqual(r.status_code, 302)
        return one("select max(id) from chemical_experiments where title=? and course_id=?",
                   title, course_id)

    def start_and_weigh(self, client, username: str, template: int,
                        title: str, weighed: str) -> int:
        """A student's whole bench visit: start the copy, weigh, done."""
        self.assertEqual(client.post(f"/chem-experiments/{template}/start").status_code, 302)
        copy = one("select max(id) from chemical_experiments where created_by=? and title=?",
                   username, title)
        self.assertIsNotNone(copy)
        self.assertEqual(client.post(f"/chem-experiments/{copy}/update",
                                     data={"weighed": weighed,
                                           "reagents": chem_tests.REAGENTS}).status_code, 302)
        return copy


class Pages(CourseCase):
    def test_the_pages_open(self):
        self.get_ok(self.a, "/chem-experiments/courses")
        self.assertIn("新建课程", self.get_ok(self.a, "/chem-experiments/courses"))

    def test_a_course_is_created_with_its_counts(self):
        course = self.make_course()
        values = row("select name, term, teacher, student_count, created_by "
                     "from experiment_courses where id=?", course)
        self.assertEqual((values[0], values[1], values[2], values[3]), ("有机化学实验", "2026-2027-1", "王老师", 30))
        self.assertEqual(values[4], self.admin)

    def test_a_course_needs_a_name(self):
        r = self.post(self.a, "/chem-experiments/courses", data={"name": ""})
        self.assertEqual(one("select count(*) from experiment_courses where name=?", ""), 0)
        self.assertFlash(r, "课程名称")

    def test_a_student_count_that_is_not_a_number_keeps_the_old_one(self):
        course = self.make_course(student_count="30")
        self.post(self.a, f"/chem-experiments/courses/{course}/update",
                  data={"student_count": "很多", "name": "有机化学实验"})
        self.assertEqual(one("select student_count from experiment_courses where id=?", course), 30)


class TheCourse(CourseCase):
    def test_the_course_page_counts_templates_copies_and_usage(self):
        self.references()
        course = self.make_course()
        template = self.make_template(course, title="课程页统计")
        # The student starts a copy and weighs at the bench.
        self.assertEqual(self.m.post(f"/chem-experiments/{template}/start").status_code, 302)
        copy = one("select max(id) from chemical_experiments where created_by=? and title=?",
                   self.member, "课程页统计")
        self.assertEqual(one("select template_id from chemical_experiments where id=?", copy), template)
        self.assertEqual(self.m.post(f"/chem-experiments/{copy}/update",
                                     data={"weighed": chem_tests.WEIGHED,
                                           "reagents": chem_tests.REAGENTS}).status_code, 302)
        self.assertFlash(self.post(self.m, f"/chem-experiments/{copy}/yield",
                                   data={"actual_grams": "0.72"}), "79.9")
        html = self.get_ok(self.m, f"/chem-experiments/courses/{course}")
        self.assertIn("课程页统计", html)                      # the template
        self.assertIn(self.member, html)                      # the student row
        self.assertIn("79.9", html)                           # their yield
        self.assertIn("1.38", html)                           # the acid's total weighed
        self.assertIn("1.021", html)                          # …and the anhydride's

    def test_two_templates_of_the_same_name_keep_their_copies_apart(self):
        course = self.make_course()
        first = self.make_template(course, title="同一名字")
        second = self.make_template(course, title="同一名字")
        self.assertNotEqual(first, second)
        self.assertEqual(self.m.post(f"/chem-experiments/{first}/start").status_code, 302)
        self.assertEqual(self.m.post(f"/chem-experiments/{second}/start").status_code, 302)
        self.assertEqual(one("select count(*) from chemical_experiments where title=? "
                             "and template_id=?", "同一名字", first), 1)
        self.assertEqual(one("select count(*) from chemical_experiments where title=? "
                             "and template_id=?", "同一名字", second), 1)

    def test_only_the_maker_or_an_admin_edits_a_course(self):
        course = self.make_course(name="别人的课")
        r = self.m.post(f"/chem-experiments/courses/{course}/update", data={"name": "改名"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(one("select name from experiment_courses where id=?", course), "别人的课")
        self.assertEqual(self.a.post(f"/chem-experiments/courses/{course}/update",
                                     data={"name": "改名"}).status_code, 302)
        self.assertEqual(one("select name from experiment_courses where id=?", course), "改名")

    def test_an_unknown_course_is_a_404(self):
        self.assertEqual(self.a.get("/chem-experiments/courses/999999").status_code, 404)


class TheUsage(CourseCase):
    def test_usage_adds_up_what_the_students_weighed(self):
        self.references()
        from app.db import SessionLocal
        course = self.make_course(name="用量统计课")
        template = self.make_template(course, title="称重练习")
        # Two students, each weighing the template's amounts at their bench.
        self.start_and_weigh(self.m, self.member, template, "称重练习", chem_tests.WEIGHED)
        self.start_and_weigh(self.o, self.other, template, "称重练习", chem_tests.WEIGHED)
        with SessionLocal() as s:
            rows = {r["cas"]: r for r in course_plans.usage(s, course_id=course)}
        self.assertAlmostEqual(rows[chem_tests.SALICYLIC]["grams"], 2 * 1.381, places=3)
        self.assertEqual(rows[chem_tests.SALICYLIC]["students"], 2)
        self.assertAlmostEqual(rows[chem_tests.SALICYLIC]["per_student"], 1.381, places=3)
        self.assertEqual(rows[chem_tests.SALICYLIC]["name"], "水杨酸")
        self.assertFalse(rows[chem_tests.SALICYLIC]["in_stock"])
        self.assertTrue(rows[chem_tests.ANHYDRIDE]["controlled"])   # the precursor flag survives the sum
        self.assertTrue(rows[chem_tests.ANHYDRIDE]["in_stock"])     # the bottle from the fixture

    def test_the_student_rows_add_up_the_copies_and_the_yields(self):
        self.references()
        course = self.make_course(name="学生汇总课")
        template = self.make_template(course, title="产率汇总")
        copy = self.start_and_weigh(self.m, self.member, template, "产率汇总", chem_tests.WEIGHED)
        self.m.post(f"/chem-experiments/{copy}/yield", data={"actual_grams": "0.72"})
        from app.db import SessionLocal
        with SessionLocal() as s:
            rows = course_plans.student_rows(s, course_id=course)
        mine = [r for r in rows if r["student"] == self.member]
        self.assertEqual(len(mine), 1)
        self.assertEqual((mine[0]["copies"], mine[0]["done"]), (1, 1))
        self.assertAlmostEqual(mine[0]["yield_avg"], 79.9, places=1)
        self.assertIsNotNone(mine[0]["last"])

    def test_a_course_with_nothing_started_has_empty_statistics(self):
        from app.db import SessionLocal
        course = self.make_course(name="空课程")
        with SessionLocal() as s:
            self.assertEqual(course_plans.usage(s, course_id=course), [])
            self.assertEqual(course_plans.student_rows(s, course_id=course), [])
        html = self.get_ok(self.a, f"/chem-experiments/courses/{course}")
        self.assertIn("还没有学生提交称量数据", html)


class TheReport(CourseCase):
    def test_the_report_page_opens_with_the_terms_numbers(self):
        self.references()
        course = self.make_course(name="报告课", student_count="30")
        template = self.make_template(course, title="报告实验")
        self.start_and_weigh(self.m, self.member, template, "报告实验", chem_tests.WEIGHED)
        html = self.get_ok(self.a, f"/chem-experiments/courses/{course}/report")
        self.assertIn("报告课", html)
        self.assertIn("水杨酸", html)                          # the usage table
        self.assertIn("41.43", html)                          # 1.381 g × 30 students
        self.assertIn("drug precursor", html)                 # the controlled table
        self.assertIn(self.member, html)                      # the student table

    def test_the_report_counts_the_shortfall_against_the_roll(self):
        from app.db import SessionLocal
        from app.models import ExperimentCourse
        course = self.make_course(name="备料课", student_count="10")
        template = self.make_template(course, title="备料实验")
        self.start_and_weigh(self.m, self.member, template, "备料实验", chem_tests.WEIGHED)
        with SessionLocal() as s:
            report = course_plans.report(s, s.get(ExperimentCourse, course))
        by_cas = {row["cas"]: row for row in report["usage"]}
        acid = by_cas[chem_tests.SALICYLIC]
        # One student weighed 1.381 g; a class of ten needs 13.81, so the
        # shortfall is what nine students have not weighed yet.
        self.assertAlmostEqual(acid["expected"], 13.81, places=2)
        self.assertAlmostEqual(acid["shortfall"], 13.81 - 1.381, places=2)
        self.assertEqual(report["roll"], 10)
        self.assertEqual(report["copies"], 1)
        self.assertEqual(len(report["controlled"]), 1)        # the anhydride
