"""jaso 명령줄 인터페이스."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, report as report_mod
from .interview import build_pack
from .lint import lint_draft
from .llm import DEFAULT_MODEL, LLMUnavailable, available as llm_available, generate
from .loader import (
    LoadError,
    load_career,
    load_company,
    load_draft,
    write_text,
    write_yaml,
)
from .matching import match_all
from .models import Answer, Draft
from .planning import plan_all, plan_question, question_prompt, system_prompt

DEFAULT_CAREER = "career.yaml"
DEFAULT_COMPANY = "company.yaml"
DEFAULT_DRAFT = "draft.yaml"
DEFAULT_OUT = "out"

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def _echo(text: str = "") -> None:
    print(text)


def _resolve_out(args, name: str) -> Path:
    return Path(args.out) / name


# --------------------------------------------------------------------------
# init
# --------------------------------------------------------------------------

def cmd_init(args) -> int:
    targets = [
        (EXAMPLES_DIR / "career_note.yaml", Path(args.career)),
        (EXAMPLES_DIR / "company.yaml", Path(args.company)),
    ]
    created = []
    for source, target in targets:
        if target.exists() and not args.force:
            _echo(f"· 이미 있음 (건너뜀): {target}   — 덮어쓰려면 --force")
            continue
        write_text(target, source.read_text(encoding="utf-8"))
        created.append(target)

    draft_path = Path(args.draft)
    if not draft_path.exists() or args.force:
        try:
            company = load_company(args.company)
            answers = [{"id": q.id, "subtitle": "", "body": "", "used": []} for q in company.questions]
        except LoadError:
            answers = []
        write_yaml(draft_path, {"answers": answers})
        created.append(draft_path)

    _echo("")
    _echo("다음 순서로 진행하세요:")
    _echo(f"  1) {args.career} 를 본인의 '실제' 경험으로 채웁니다 (지어내지 않기).")
    _echo(f"  2) {args.company} 에 공고 원문(문항·글자수·인재상)을 그대로 옮깁니다.")
    _echo("  3) jaso match   — 어떤 경험이 이 회사에 맞는지 확인")
    _echo("  4) jaso plan    — 문항별 문단 구성과 쓸 경험 확정")
    _echo("  5) jaso prompt  — 프롬프트 생성 (또는 jaso draft 로 자동 초안)")
    _echo(f"  6) {args.draft} 에 초안을 붙여넣고 jaso lint 로 검증")
    _echo("  7) jaso interview — 면접 예상질문/준비표 생성")
    if created:
        _echo("")
        _echo("생성된 파일: " + ", ".join(str(p) for p in created))
    return 0


# --------------------------------------------------------------------------
# match / plan
# --------------------------------------------------------------------------

def cmd_match(args) -> int:
    note = load_career(args.career)
    company = load_company(args.company)

    _echo(f"■ {company.role_label()}")
    _echo("")
    for match in match_all(note, company):
        _echo(f"  [{match.total:>3}점] {match.experience.id}  {match.experience.label()}")
        for reason in match.evidence():
            _echo(f"          - {reason}")
    _echo("")

    if args.write:
        md = _resolve_out(args, "match.md")
        csv_path = _resolve_out(args, "match.csv")
        write_text(md, report_mod.match_markdown(note, company))
        write_text(csv_path, report_mod.match_csv(note, company))
        _echo(f"저장: {md}, {csv_path}")
    return 0


def cmd_plan(args) -> int:
    note = load_career(args.career)
    company = load_company(args.company)
    plans = plan_all(note, company)

    for plan in plans:
        question = plan.question
        _echo(f"■ [{question.id}] {question.text}")
        _echo(f"   유형 {question.type} · {question.limit.describe()} · 목표 {plan.target_chars}자")
        for slot in plan.paragraphs:
            _echo(f"     - {slot.name:<14} {slot.share:>3}%  ≈{slot.chars:>4}자  {slot.guide}")
        if plan.picks:
            best = plan.picks[0]
            _echo(f"     ★ 주 경험: {best[0].experience.id} ({best[1]}점) {best[0].experience.label()}")
            for other, score, _ in plan.picks[1:]:
                _echo(f"       대안: {other.experience.id} ({score}점)")
        for candidate in plan.subtitle_candidates[:2]:
            _echo(f"     · 소제목 후보: {candidate}")
        for warning in plan.warnings:
            _echo(f"     ⚠ {warning}")
        _echo("")

    if args.write:
        path = _resolve_out(args, "plan.md")
        write_text(path, report_mod.plan_markdown(plans, note, company))
        _echo(f"저장: {path}")
    return 0


# --------------------------------------------------------------------------
# prompt / draft
# --------------------------------------------------------------------------

def _plans_for(args, note, company):
    if args.question:
        question = company.question(args.question)
        if question is None:
            raise LoadError(f"문항 id를 찾을 수 없습니다: {args.question}")
        return [plan_question(question, note, company)]
    return plan_all(note, company)


def cmd_prompt(args) -> int:
    note = load_career(args.career)
    company = load_company(args.company)
    plans = _plans_for(args, note, company)

    blocks = []
    for plan in plans:
        blocks.append(
            f"===== [{plan.question.id}] 프롬프트 =====\n\n"
            f"--- 시스템 프롬프트 ---\n{system_prompt()}\n\n"
            f"--- 사용자 프롬프트 ---\n{question_prompt(plan, note, company)}\n"
        )
    text = "\n\n".join(blocks)

    if args.write:
        path = _resolve_out(args, "prompts.md")
        write_text(path, text)
        _echo(f"저장: {path}")
        _echo("이 파일 내용을 Claude 앱에 그대로 붙여넣으면 초안이 나옵니다.")
    else:
        _echo(text)
    return 0


def cmd_draft(args) -> int:
    note = load_career(args.career)
    company = load_company(args.company)
    plans = _plans_for(args, note, company)

    if not llm_available():
        _echo("· API 키가 없어 자동 생성은 건너뜁니다.")
        _echo("  jaso prompt --write 로 프롬프트를 만들어 Claude 앱에 붙여넣으세요.")
        return cmd_prompt(args)

    draft_path = Path(args.draft)
    try:
        draft = load_draft(draft_path)
    except LoadError:
        draft = Draft()

    for plan in plans:
        qid = plan.question.id
        _echo(f"· [{qid}] 생성 중… (model={args.model})")
        try:
            result = generate(system_prompt(), question_prompt(plan, note, company), args.model)
        except LLMUnavailable as exc:
            _echo(f"  ✗ {exc}")
            return 1
        answer = draft.answer(qid)
        if answer is None:
            answer = Answer(id=qid)
            draft.answers.append(answer)
        answer.subtitle = result.subtitle
        answer.body = result.body
        answer.note = result.todo
        answer.used = [p[0].experience.id for p in plan.picks[:1]]
        _echo(f"  → 소제목: {result.subtitle or '(없음)'}")
        if result.todo:
            _echo(f"  ⚠ 확인 필요: {result.todo}")

    write_yaml(draft_path, {
        "company": company.name,
        "position": company.position,
        "answers": [
            {"id": a.id, "subtitle": a.subtitle, "body": a.body, "used": a.used, "note": a.note}
            for a in draft.answers
        ],
    })
    _echo("")
    _echo(f"저장: {draft_path}")
    _echo("초안은 반드시 본인이 읽고 사실 여부를 확인한 뒤 jaso lint 로 검증하세요.")
    return 0


# --------------------------------------------------------------------------
# lint / interview / export
# --------------------------------------------------------------------------

def cmd_lint(args) -> int:
    note = load_career(args.career)
    company = load_company(args.company)
    draft = load_draft(args.draft)
    result = lint_draft(draft, note, company)

    for question in company.questions:
        findings = result.for_question(question.id)
        if not findings:
            continue
        _echo(f"■ [{question.id}] {question.text[:40]}")
        for finding in sorted(findings, key=lambda f: {"ERROR": 0, "WARN": 1, "INFO": 2}[f.level]):
            _echo(finding.format())
        _echo("")

    errors = result.errors()
    warns = [f for f in result.findings if f.level == "WARN"]
    _echo(f"요약: 오류 {len(errors)}건, 경고 {len(warns)}건")

    if args.write:
        path = _resolve_out(args, "lint.md")
        write_text(path, report_mod.lint_markdown(result, company))
        _echo(f"저장: {path}")
    return 1 if errors and args.strict else 0


def cmd_interview(args) -> int:
    note = load_career(args.career)
    company = load_company(args.company)
    try:
        draft = load_draft(args.draft)
    except LoadError:
        draft = Draft()
    pack = build_pack(draft, note, company)

    for category, items in pack.by_category().items():
        _echo(f"■ {category}")
        for item in items:
            _echo(f"  ({item.risk}) {item.question}")
            if item.prep:
                _echo(f"        └ {item.prep}")
        _echo("")
    if pack.gaps:
        _echo("■ 보강 필요")
        for gap in pack.gaps:
            _echo(f"  ⚠ {gap}")
        _echo("")

    if args.write:
        md = _resolve_out(args, "interview.md")
        csv_path = _resolve_out(args, "interview.csv")
        write_text(md, report_mod.interview_markdown(pack, company))
        write_text(csv_path, report_mod.interview_csv(pack))
        _echo(f"저장: {md}, {csv_path}  (csv는 Excel에서 바로 열립니다)")
    return 0


def cmd_export(args) -> int:
    note = load_career(args.career)
    company = load_company(args.company)
    draft = load_draft(args.draft)
    result = lint_draft(draft, note, company)
    pack = build_pack(draft, note, company)

    outputs = {
        "match.md": report_mod.match_markdown(note, company),
        "match.csv": report_mod.match_csv(note, company),
        "plan.md": report_mod.plan_markdown(plan_all(note, company), note, company),
        "lint.md": report_mod.lint_markdown(result, company),
        "자기소개서.md": report_mod.final_markdown(draft, company, result),
        "interview.md": report_mod.interview_markdown(pack, company),
        "interview.csv": report_mod.interview_csv(pack),
    }
    for name, content in outputs.items():
        write_text(_resolve_out(args, name), content)
    _echo(f"{len(outputs)}개 파일을 {args.out}/ 에 저장했습니다.")
    for name in outputs:
        _echo(f"  - {args.out}/{name}")
    errors = result.errors()
    if errors:
        _echo("")
        _echo(f"⚠ 검증 오류 {len(errors)}건이 남아 있습니다. lint.md 를 먼저 확인하세요.")
    return 0


# --------------------------------------------------------------------------
# 엔트리포인트
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jaso",
        description="경력 노트로 회사 맞춤 자기소개서와 면접 준비 자료를 만드는 도구",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="예) jaso init → jaso match → jaso plan → jaso prompt → jaso lint → jaso interview",
    )
    parser.add_argument("--version", action="version", version=f"jaso {__version__}")
    parser.add_argument("--career", default=DEFAULT_CAREER, help="경력 노트 파일 (기본 career.yaml)")
    parser.add_argument("--company", default=DEFAULT_COMPANY, help="회사/문항 파일 (기본 company.yaml)")
    parser.add_argument("--draft", default=DEFAULT_DRAFT, help="초안 파일 (기본 draft.yaml)")
    parser.add_argument("--out", default=DEFAULT_OUT, help="산출물 폴더 (기본 out/)")

    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="템플릿 파일 생성")
    p_init.add_argument("--force", action="store_true", help="기존 파일 덮어쓰기")
    p_init.set_defaults(func=cmd_init)

    p_match = sub.add_parser("match", help="인재상 ↔ 경험 매칭")
    p_match.add_argument("--write", action="store_true", help="out/ 에 리포트 저장")
    p_match.set_defaults(func=cmd_match)

    p_plan = sub.add_parser("plan", help="문항별 문단 구성 설계")
    p_plan.add_argument("--write", action="store_true")
    p_plan.set_defaults(func=cmd_plan)

    p_prompt = sub.add_parser("prompt", help="문항별 LLM 프롬프트 생성")
    p_prompt.add_argument("-q", "--question", help="특정 문항만 (예: q1)")
    p_prompt.add_argument("--write", action="store_true")
    p_prompt.set_defaults(func=cmd_prompt)

    p_draft = sub.add_parser("draft", help="초안 자동 생성 (API 키 필요)")
    p_draft.add_argument("-q", "--question")
    p_draft.add_argument("--model", default=DEFAULT_MODEL)
    p_draft.add_argument("--write", action="store_true", help="(프롬프트로 대체될 때) 파일 저장")
    p_draft.set_defaults(func=cmd_draft)

    p_lint = sub.add_parser("lint", help="초안 검증 (글자수/수치/사실/클리셰)")
    p_lint.add_argument("--write", action="store_true")
    p_lint.add_argument("--strict", action="store_true", help="오류가 있으면 종료코드 1")
    p_lint.set_defaults(func=cmd_lint)

    p_interview = sub.add_parser("interview", help="면접 예상질문/준비표 생성")
    p_interview.add_argument("--write", action="store_true")
    p_interview.set_defaults(func=cmd_interview)

    p_export = sub.add_parser("export", help="모든 산출물을 out/ 에 저장")
    p_export.set_defaults(func=cmd_export)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except LoadError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
