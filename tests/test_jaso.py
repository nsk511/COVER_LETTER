"""jaso 핵심 로직 테스트 — python3 -m unittest discover -s tests"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jaso import loader, matching, planning, textutil  # noqa: E402
from jaso.interview import build_pack  # noqa: E402
from jaso.lint import lint_draft  # noqa: E402
from jaso.models import Answer, CompanyProfile, Draft  # noqa: E402

CAREER = ROOT / "examples" / "career_note.yaml"
COMPANY = ROOT / "examples" / "company.yaml"


def load():
    return loader.load_career(CAREER), loader.load_company(COMPANY)


class TextUtilTest(unittest.TestCase):
    def test_count_chars_counts_newline_as_one(self):
        self.assertEqual(textutil.count_chars("가나\n다 라"), (6, 4))

    def test_extract_numbers_keeps_unit(self):
        found = textutil.extract_numbers("90분에서 20분으로 78% 줄였고 1,200건입니다")
        self.assertEqual(found, ["90분", "20분", "78%", "1,200건"])

    def test_canonical_number_strips_comma_and_space(self):
        self.assertEqual(textutil.canonical_number("1,200 건"), "1200건")

    def test_count_for_mode(self):
        self.assertEqual(textutil.count_for_mode("가 나", "without_space"), 2)
        self.assertEqual(textutil.count_for_mode("가 나", "with_space"), 3)


class MatchingTest(unittest.TestCase):
    def test_resolve_axes_maps_korean_phrases(self):
        _, company = load()
        axes = {a.source: a.axis for a in matching.resolve_axes(company)}
        self.assertEqual(axes["도전하는 사람"], "도전·혁신")
        self.assertEqual(axes["신뢰받는 사람"], "정직·신뢰")

    def test_unknown_talent_phrase_becomes_its_own_axis(self):
        company = CompanyProfile(name="X", talent_profile=["우주최강 마인드"])
        axes = matching.resolve_axes(company)
        self.assertEqual(len(axes), 1)
        self.assertFalse(axes[0].mapped)

    def test_user_specified_experience_wins(self):
        note, company = load()
        question = company.question("q2")
        picks = matching.recommend(note, company, question)
        self.assertEqual(picks[0][0].experience.id, "exp-rate-agg")

    def test_coverage_reports_supporting_experiences(self):
        note, company = load()
        result = matching.coverage(note, company)
        self.assertIn("exp-rate-agg", result["전문성"])


class PlanningTest(unittest.TestCase):
    def test_paragraph_shares_sum_to_100(self):
        for name, layout in planning.PARAGRAPH_PLANS.items():
            self.assertEqual(sum(share for _, share, _ in layout), 100, name)

    def test_prompt_contains_rules_and_material(self):
        note, company = load()
        plan = planning.plan_question(company.question("q2"), note, company)
        prompt = planning.question_prompt(plan, note, company)
        self.assertIn("쓸 수 있는 재료", prompt)
        self.assertIn("exp-rate-agg", prompt)
        self.assertIn("90분", prompt)

    def test_motivation_without_research_warns(self):
        note, company = load()
        plan = planning.plan_question(company.question("q1"), note, company)
        self.assertTrue(any("리서치" in w for w in plan.warnings))


class LintTest(unittest.TestCase):
    def _lint(self, answer: Answer):
        note, company = load()
        return lint_draft(Draft(answers=[answer]), note, company)

    def test_invented_number_is_error(self):
        report = self._lint(Answer(id="q2", subtitle="집계 단위를 바꿔 78% 단축", body="정확도 99.8%를 유지했습니다."))
        rules = [f.rule for f in report.errors()]
        self.assertIn("NUM", rules)

    def test_number_from_career_note_is_allowed(self):
        report = self._lint(Answer(id="q2", subtitle="집계 단위를 바꿔 78% 단축", body="90분이 20분으로 줄었습니다."))
        self.assertNotIn("NUM", [f.rule for f in report.errors()])

    def test_fatal_weakness_on_core_competency(self):
        report = self._lint(Answer(id="q3", subtitle="강점", body="저는 보고서 작성이 서툽니다."))
        weak = [f for f in report.findings if f.rule == "WEAK" and f.level == "ERROR"]
        self.assertTrue(weak)

    def test_cliche_detected(self):
        report = self._lint(Answer(id="q2", subtitle="x", body="쿼리 최적화를 수행했습니다."))
        self.assertIn("CLICHE", [f.rule for f in report.findings])

    def test_company_story_balance(self):
        body = ("가나손해보험의 창업 이념과 경영철학에 공감했습니다. "
                "가나손해보험의 비전은 훌륭합니다. 저는 열심히 하겠습니다.")
        report = self._lint(Answer(id="q1", subtitle="x", body=body))
        self.assertIn("BALANCE", [f.rule for f in report.errors()])

    def test_missing_answer_is_error(self):
        note, company = load()
        report = lint_draft(Draft(), note, company)
        self.assertEqual(len([f for f in report.errors() if f.rule == "MISSING"]), 4)

    def test_length_limit(self):
        report = self._lint(Answer(id="q3", subtitle="x", body="가" * 900))
        self.assertIn("LEN", [f.rule for f in report.errors()])


class InterviewTest(unittest.TestCase):
    def test_numbers_produce_followup_questions(self):
        note, company = load()
        draft = Draft(answers=[Answer(id="q2", subtitle="x", body="90분을 20분으로 줄였습니다.", used=["exp-rate-agg"])])
        pack = build_pack(draft, note, company)
        self.assertTrue(any(q.category == "수치 검증" for q in pack.questions))

    def test_domain_term_produces_question(self):
        note, company = load()
        draft = Draft(answers=[Answer(id="q2", subtitle="x", body="요율산출 로직을 재설계했습니다.")])
        pack = build_pack(draft, note, company)
        self.assertTrue(any("요율산출" in q.question for q in pack.questions))

    def test_script_marks_missing_insight(self):
        note, company = load()
        exp = note.by_id("exp-rate-agg")
        exp.insight = ""
        from jaso.interview import script_for
        self.assertIn("⚠ 미작성", script_for(exp))


if __name__ == "__main__":
    unittest.main()
