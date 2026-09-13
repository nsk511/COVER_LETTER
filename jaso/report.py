"""산출물 생성 — Markdown 리포트와 Excel(CSV) 파일."""

from __future__ import annotations

import csv
import io
from datetime import date

from .interview import InterviewPack
from .lint import LintReport
from .matching import match_all, resolve_axes, coverage
from .models import CareerNote, CompanyProfile, Draft
from .planning import QuestionPlan
from .textutil import count_chars, truncate


def _header(company: CompanyProfile, title: str) -> list[str]:
    return [
        f"# {title}",
        "",
        f"- 회사/직무: **{company.role_label() or company.name}**",
        f"- 작성일: {date.today().isoformat()}",
        "",
    ]


# --------------------------------------------------------------------------
# 매칭 리포트
# --------------------------------------------------------------------------

def match_markdown(note: CareerNote, company: CompanyProfile) -> str:
    axes = resolve_axes(company)
    lines = _header(company, "인재상 ↔ 경험 매칭")

    lines += ["## 1. 인재상 해석", "", "| 회사 인재상 원문 | 역량축 | 사전 매핑 |", "|---|---|---|"]
    for axis in axes:
        lines.append(f"| {axis.source} | {axis.axis} | {'○' if axis.mapped else '✗ (직접 해석)'} |")

    lines += ["", "## 2. 경험별 점수", "", "| 경험 | 총점 | 근거 |", "|---|---|---|"]
    for match in match_all(note, company):
        evidence = "<br>".join(match.evidence()) or "-"
        lines.append(f"| `{match.experience.id}` {match.experience.label()} | {match.total} | {evidence} |")

    lines += ["", "## 3. 인재상 커버리지", ""]
    gaps = []
    for axis_name, exp_ids in coverage(note, company).items():
        if exp_ids:
            lines.append(f"- **{axis_name}**: {', '.join(exp_ids)}")
        else:
            lines.append(f"- **{axis_name}**: ⚠ 뒷받침할 경험 없음")
            gaps.append(axis_name)
    if gaps:
        lines += [
            "",
            f"> 비어 있는 축({', '.join(gaps)})은 자소서에서 억지로 만들지 말고, "
            "실제 경험이 있는지 다시 떠올려 경력 노트에 추가하세요. 없으면 그 축은 비워둡니다.",
        ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# 설계 리포트
# --------------------------------------------------------------------------

def plan_markdown(plans: list[QuestionPlan], note: CareerNote, company: CompanyProfile) -> str:
    lines = _header(company, "문항별 작성 설계")
    for plan in plans:
        question = plan.question
        lines += [
            f"## [{question.id}] {question.text}",
            "",
            f"- 유형: `{question.type}` · 글자수: {question.limit.describe()} · 목표 {plan.target_chars}자",
            "",
            "**문단 구성**",
            "",
            "| 문단 | 배분 | 목표 글자수 | 쓰는 법 |",
            "|---|---|---|---|",
        ]
        for slot in plan.paragraphs:
            lines.append(f"| {slot.name} | {slot.share}% | {slot.chars}자 | {slot.guide or '-'} |")

        lines += ["", "**쓸 경험(추천순)**", ""]
        if plan.picks:
            for rank, (match, score, reasons) in enumerate(plan.picks, 1):
                exp = match.experience
                mark = "★" if rank == 1 else " "
                lines.append(f"{rank}. {mark} `{exp.id}` {exp.label()} — {score}점")
                lines.append(f"   - 근거: {'; '.join(reasons[:4]) or '-'}")
                if exp.star_gaps():
                    lines.append(f"   - ⚠ 보강 필요: {', '.join(exp.star_gaps())}")
        else:
            lines.append("- (추천할 경험 없음)")

        if plan.subtitle_candidates:
            lines += ["", "**소제목 후보** (그대로 쓰지 말고 다듬을 것)", ""]
            lines += [f"- {c}" for c in plan.subtitle_candidates]

        if plan.warnings:
            lines += ["", "**확인 필요**", ""]
            lines += [f"- ⚠ {w}" for w in plan.warnings]
        lines.append("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# 검증 리포트
# --------------------------------------------------------------------------

def lint_markdown(report: LintReport, company: CompanyProfile) -> str:
    lines = _header(company, "초안 검증 결과")
    errors = report.errors()
    warns = [f for f in report.findings if f.level == "WARN"]
    lines += [
        f"**요약: 오류 {len(errors)}건 · 경고 {len(warns)}건**",
        "",
        "" if report.ok() else "> 오류(✗)는 제출 전에 반드시 고쳐야 합니다.",
        "",
    ]
    for question in company.questions:
        findings = report.for_question(question.id)
        if not findings:
            continue
        counts = report.counts.get(question.id)
        count_note = f" · 공백포함 {counts[0]}자 / 공백제외 {counts[1]}자" if counts else ""
        lines += [f"## [{question.id}] {truncate(question.text, 40)}{count_note}", ""]
        for finding in sorted(findings, key=lambda f: {"ERROR": 0, "WARN": 1, "INFO": 2}[f.level]):
            lines.append("```")
            lines.append(finding.format())
            lines.append("```")
        lines.append("")
    orphan = [f for f in report.findings if not any(f.question_id == q.id for q in company.questions)]
    if orphan:
        lines += ["## 기타", ""] + [f"- {f.format().strip()}" for f in orphan]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# 제출용 최종본
# --------------------------------------------------------------------------

def final_markdown(draft: Draft, company: CompanyProfile, report: LintReport | None = None) -> str:
    lines = [
        f"# {company.name} 자기소개서",
        "",
        f"- 지원 직무: {company.position}" + (f" ({company.team})" if company.team else ""),
        f"- 작성일: {date.today().isoformat()}",
        "",
        "---",
        "",
    ]
    for question in company.questions:
        answer = draft.answer(question.id)
        lines.append(f"## {question.text}")
        if answer is None or not answer.body:
            lines += ["", "> ⚠ 미작성", "", "---", ""]
            continue
        with_space, without_space = count_chars(answer.full_text())
        lines += [
            "",
            f"**[{answer.subtitle or '소제목 없음'}]**",
            "",
            f"> {question.limit.describe()} · 실제 공백포함 {with_space}자 / 공백제외 {without_space}자",
            "",
            answer.body,
            "",
        ]
        if answer.note:
            lines += [f"<small>확인 필요: {answer.note}</small>", ""]
        lines += ["---", ""]

    if report:
        todo = [f for f in report.findings if f.level in ("ERROR", "WARN")]
        if todo:
            lines += ["### 제출 전 확인 사항", ""]
            lines += [f"- [{f.level}] ({f.question_id}) {f.message}" for f in todo]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# 면접 준비 자료
# --------------------------------------------------------------------------

def interview_markdown(pack: InterviewPack, company: CompanyProfile) -> str:
    lines = _header(company, "면접 예상질문 및 준비표")
    high = [q for q in pack.questions if q.risk == "높음"]
    lines += [f"**총 {len(pack.questions)}문항 · 우선 준비 {len(high)}문항**", ""]

    for category, items in pack.by_category().items():
        lines += [f"## {category}", ""]
        for item in items:
            lines.append(f"- **({item.risk}) {item.question}**")
            if item.source:
                lines.append(f"  - 출처: {item.source}")
            if item.prep:
                lines.append(f"  - 답변 뼈대: {item.prep}")
        lines.append("")

    if pack.scripts:
        lines += ["## 경험별 구술 스크립트", ""]
        for _, script in pack.scripts:
            lines += ["```", script, "```", ""]

    if pack.gaps:
        lines += ["## 보강이 필요한 부분", ""]
        lines += [f"- ⚠ {gap}" for gap in pack.gaps]
    return "\n".join(lines) + "\n"


def _csv(rows: list[list[str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerows(rows)
    # Excel에서 한글이 깨지지 않도록 BOM을 붙인다.
    return "﻿" + buffer.getvalue()


def interview_csv(pack: InterviewPack) -> str:
    rows = [["우선순위", "분류", "예상질문", "자소서 근거", "답변 뼈대", "준비완료(O/X)", "내 답변 메모"]]
    for item in pack.questions:
        rows.append([item.risk, item.category, item.question, item.source, item.prep, "", ""])
    return _csv(rows)


def match_csv(note: CareerNote, company: CompanyProfile) -> str:
    axes = resolve_axes(company)
    header = ["경험ID", "경험명", "총점", "직무적합"] + [a.axis for a in axes] + ["비고"]
    rows = [header]
    for match in match_all(note, company):
        row = [
            match.experience.id,
            match.experience.label(),
            str(match.total),
            str(match.job_fit),
        ]
        row += [str(match.axis_scores.get(a.axis, 0)) for a in axes]
        row.append("; ".join(match.bonuses))
        rows.append(row)
    return _csv(rows)
