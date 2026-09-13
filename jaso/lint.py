"""자소서 초안 검증기.

자소서에서 사람이 놓치기 쉬운 것들을 기계적으로 잡아낸다.
가장 중요한 규칙은 FACT/NUM — 경력 노트에 없는 수치나 출처 없는 회사 사실이
초안에 들어오는 것을 막는 것이다(= 지어내기 방지).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .loader import lint_rules
from .models import Answer, CareerNote, CompanyProfile, Question
from .textutil import (
    canonical_number,
    contains_any,
    count_chars,
    count_for_mode,
    extract_numbers,
    number_only,
    split_sentences,
    truncate,
)

ERROR = "ERROR"
WARN = "WARN"
INFO = "INFO"

_LEVEL_ORDER = {ERROR: 0, WARN: 1, INFO: 2}


@dataclass
class Finding:
    rule: str
    level: str
    question_id: str
    message: str
    hint: str = ""
    evidence: str = ""

    def format(self) -> str:
        mark = {"ERROR": "✗", "WARN": "!", "INFO": "·"}[self.level]
        line = f"  {mark} [{self.rule}] {self.message}"
        if self.evidence:
            line += f"\n      근거: {self.evidence}"
        if self.hint:
            line += f"\n      조치: {self.hint}"
        return line


@dataclass
class LintReport:
    findings: list[Finding] = field(default_factory=list)
    counts: dict[str, tuple[int, int]] = field(default_factory=dict)  # qid -> (공백포함, 공백제외)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def for_question(self, qid: str) -> list[Finding]:
        return [f for f in self.findings if f.question_id == qid]

    def sorted(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: (_LEVEL_ORDER[f.level], f.question_id, f.rule))

    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == ERROR]

    def ok(self) -> bool:
        return not self.errors()


# --------------------------------------------------------------------------
# 개별 규칙
# --------------------------------------------------------------------------

def check_length(answer: Answer, question: Question, report: LintReport) -> None:
    """글자수 — 공백포함/제외 모두 계산하고 문항 기준으로 판정한다."""
    text = answer.full_text()
    with_space, without_space = count_chars(text)
    report.counts[question.id] = (with_space, without_space)

    limit = question.limit
    actual = count_for_mode(text, limit.count_mode)
    mode_label = "공백포함" if limit.count_mode == "with_space" else "공백제외"

    if limit.max and actual > limit.max:
        report.add(Finding(
            "LEN", ERROR, question.id,
            f"글자수 초과: {actual}자 / 최대 {limit.max}자({mode_label}) — {actual - limit.max}자 줄여야 합니다",
            hint="회사 설명·수식어부터 줄이고 본인 행동/결과는 남깁니다",
        ))
    elif limit.min and actual < limit.min:
        report.add(Finding(
            "LEN", ERROR, question.id,
            f"글자수 미달: {actual}자 / 최소 {limit.min}자({mode_label}) — {limit.min - actual}자 더 필요합니다",
            hint="경험의 '어려움'과 '왜 그 방법이 가능했는지'를 보강하면 자연스럽게 늘어납니다",
        ))
    elif limit.max and not limit.min and actual < limit.max * 0.8:
        report.add(Finding(
            "LEN", WARN, question.id,
            f"분량 여유: {actual}자 / 최대 {limit.max}자({mode_label}) — 80% 미만입니다",
            hint="제한의 90% 내외까지 채우는 것이 일반적입니다",
        ))
    else:
        report.add(Finding(
            "LEN", INFO, question.id,
            f"글자수 {actual}자 ({limit.describe()}) · 공백포함 {with_space} / 공백제외 {without_space}",
        ))


def check_subtitle(answer: Answer, question: Question, company: CompanyProfile,
                   report: LintReport) -> None:
    """소제목 유무와 [방법]+[결과] 공식 준수 여부."""
    if not answer.subtitle:
        report.add(Finding(
            "SUB", ERROR, question.id,
            "소제목이 없습니다",
            hint="기본 공식 [방법(how)] + [결과(result)]. 지원동기 문항은 테마+회사명도 가능합니다",
        ))
        return

    subtitle = answer.subtitle
    result_markers = ["줄", "단축", "개선", "높", "낮", "확보", "해결", "만들", "없앤",
                      "0건", "%", "배", "시간", "달성", "이끈", "바꾼"]
    method_markers = ["로", "으로", "통해", "한", "하여", "써서", "재설계", "표준화", "분석"]
    has_result = bool(contains_any(subtitle, result_markers))
    has_method = bool(contains_any(subtitle, method_markers))

    if question.type != "motivation" and not (has_result and has_method):
        missing = []
        if not has_method:
            missing.append("방법(how)")
        if not has_result:
            missing.append("결과(result)")
        report.add(Finding(
            "SUB", WARN, question.id,
            f"소제목에 {', '.join(missing)} 가 드러나지 않습니다: 「{subtitle}」",
            hint="예) '집계 단위를 바꿔 산출 시간을 78% 줄인 경험'",
        ))

    if company.team and company.team in subtitle:
        report.add(Finding(
            "SUB", WARN, question.id,
            f"소제목이 특정 팀({company.team})에만 해당하는 표현입니다",
            hint="모집부문이 여러 팀이면 좁은 표현은 피합니다",
        ))


def check_numbers(answer: Answer, question: Question, note: CareerNote,
                  company: CompanyProfile, report: LintReport) -> None:
    """초안에 있는 수치가 경력 노트/리서치에 실재하는지 대조한다."""
    allowed: set[str] = set()
    for token in extract_numbers(note.all_text()):
        allowed.add(canonical_number(token))
        allowed.add(number_only(token))
    for item in company.research:
        for token in extract_numbers(f"{item.claim} {item.date}"):
            allowed.add(canonical_number(token))
            allowed.add(number_only(token))
    for token in extract_numbers(question.text):
        allowed.add(canonical_number(token))
        allowed.add(number_only(token))

    for token in extract_numbers(answer.full_text()):
        canon, bare = canonical_number(token), number_only(token)
        if canon in allowed or bare in allowed:
            continue
        report.add(Finding(
            "NUM", ERROR, question.id,
            f"경력 노트에 없는 수치입니다: 「{token}」",
            hint="실제 수치로 고치거나, 근거를 경력 노트(metrics)에 먼저 추가하세요. 지어낸 숫자는 면접에서 바로 무너집니다",
        ))


def check_cliches(answer: Answer, question: Question, report: LintReport) -> None:
    rules = lint_rules()
    text = answer.full_text()
    for item in rules.get("cliches", []):
        phrase = item.get("phrase", "")
        if contains_any(text, [phrase]):
            report.add(Finding(
                "CLICHE", WARN, question.id,
                f"뭉뚱그린 표현: 「{phrase}」",
                hint=item.get("why", ""),
            ))


def check_overtime(answer: Answer, question: Question, report: LintReport) -> None:
    rules = lint_rules()
    hits = contains_any(answer.full_text(), rules.get("overtime_markers", []))
    for hit in hits:
        report.add(Finding(
            "OVERTIME", WARN, question.id,
            f"근무 외 시간을 강조하는 표현: 「{hit}」",
            hint="'언제 했는지'보다 '무엇을 분석해 무엇을 바꿨는지'로 씁니다",
        ))


def check_weakness(answer: Answer, question: Question, company: CompanyProfile,
                   note: CareerNote, report: LintReport) -> None:
    """약점 문항: 직무 핵심역량과 직결되는 약점은 치명적이다."""
    if question.type != "strength_weakness":
        return
    rules = lint_rules()
    text = answer.full_text()

    for pattern in rules.get("fatal_weakness_patterns", []):
        if not contains_any(text, [pattern]):
            continue
        for sentence in split_sentences(text):
            if pattern not in sentence.replace(" ", "") and pattern not in sentence:
                continue
            core_hits = contains_any(sentence, company.core_competencies)
            level = ERROR if core_hits else WARN
            extra = f" — 직무 핵심역량({', '.join(core_hits)})과 직결됩니다" if core_hits else ""
            report.add(Finding(
                "WEAK", level, question.id,
                f"단정형 약점 표현: 「{pattern}」{extra}",
                hint="'부족했다'가 아니라 '~에 집중하다 보니 ~하는 데 더 많은 노력이 필요했다'로 톤을 조정하고, "
                     "경력 노트에 관련 경험이 있다면 개선 중인 지점으로 씁니다",
                evidence=truncate(sentence, 60),
            ))
            break

    if not any(w.offset_by or w.improving for w in note.weaknesses):
        report.add(Finding(
            "WEAK", INFO, question.id,
            "경력 노트의 약점에 improving/offset_by 가 비어 있습니다",
            hint="약점은 같은 강점으로 보완/극복 중이라는 구조로 연결해야 합니다",
        ))


def check_company_facts(answer: Answer, question: Question, company: CompanyProfile,
                        report: LintReport) -> None:
    """회사 관련 사실 주장이 확인된 리서치에 근거하는지."""
    rules = lint_rules()
    markers = rules.get("company_fact_markers", [])
    usable = company.usable_research()
    text = answer.full_text()

    for sentence in split_sentences(text):
        if company.name and company.name not in sentence:
            continue
        if not contains_any(sentence, markers):
            continue
        supported = False
        for item in usable:
            claim_tokens = [t for t in item.claim.replace(",", " ").split() if len(t) >= 2]
            if claim_tokens and contains_any(sentence, claim_tokens):
                supported = True
                break
        if not supported:
            report.add(Finding(
                "FACT", ERROR, question.id,
                "출처로 확인되지 않은 회사 관련 주장입니다",
                hint="company.yaml 의 research 에 출처(source)와 checked: true 를 추가하거나, 문장을 삭제하세요",
                evidence=truncate(sentence, 60),
            ))

    unchecked = [r for r in company.research if r.claim and not r.checked]
    if unchecked and question.type == "motivation":
        report.add(Finding(
            "FACT", WARN, question.id,
            f"미확인 리서치 {len(unchecked)}건이 남아 있습니다",
            hint="지원 시점 기준 최신(가급적 올해) 자료인지 다시 확인한 뒤 checked: true 로 바꾸세요",
            evidence="; ".join(truncate(r.claim, 30) for r in unchecked[:3]),
        ))


def check_motivation_balance(answer: Answer, question: Question, company: CompanyProfile,
                             report: LintReport) -> None:
    """지원동기: 회사 이야기가 본문 절반을 넘으면 '왜 나인가'가 밀린다."""
    if question.type != "motivation":
        return
    rules = lint_rules()
    markers = rules.get("company_story_markers", []) + ([company.name] if company.name else [])
    sentences = split_sentences(answer.body)
    if not sentences:
        return
    company_chars = sum(len(s) for s in sentences if contains_any(s, markers))
    total = sum(len(s) for s in sentences)
    share = company_chars / total if total else 0
    if share > 0.5:
        report.add(Finding(
            "BALANCE", ERROR, question.id,
            f"회사 이야기 비중이 {share:.0%}입니다 (기준 50% 이하)",
            hint="회사 연혁·철학은 한두 문장 배경으로 줄이고, 절반 이상을 본인 경험과 포부에 씁니다",
        ))
    elif share > 0.35:
        report.add(Finding(
            "BALANCE", WARN, question.id,
            f"회사 이야기 비중 {share:.0%} — 조금 더 줄이는 편이 안전합니다",
        ))


def check_sentences(answer: Answer, question: Question, report: LintReport) -> None:
    rules = lint_rules().get("sentence", {})
    max_chars = int(rules.get("max_chars", 95))
    warn_ratio = float(rules.get("warn_ratio", 0.25))
    sentences = split_sentences(answer.body)
    if not sentences:
        report.add(Finding("EMPTY", ERROR, question.id, "본문이 비어 있습니다"))
        return
    long_ones = [s for s in sentences if len(s) > max_chars]
    if long_ones and len(long_ones) / len(sentences) > warn_ratio:
        report.add(Finding(
            "SENT", WARN, question.id,
            f"{max_chars}자를 넘는 긴 문장이 {len(long_ones)}/{len(sentences)}개입니다",
            hint="한 문장에 한 가지만 담으면 읽는 속도가 빨라집니다",
            evidence=truncate(long_ones[0], 50),
        ))


def check_evidence_links(answer: Answer, question: Question, note: CareerNote,
                         report: LintReport) -> None:
    """used 에 적힌 경험 id가 실제로 존재하는지 + 대외비 경험 사용 경고."""
    for exp_id in answer.used:
        exp = note.by_id(exp_id)
        if exp is None:
            report.add(Finding(
                "REF", ERROR, question.id,
                f"존재하지 않는 경험 id 를 참조합니다: {exp_id}",
            ))
            continue
        if exp.confidential:
            report.add(Finding(
                "REF", WARN, question.id,
                f"대외비로 표시된 경험을 사용했습니다: {exp_id}",
                hint="고객사명 등은 'A사', '대형 손해보험사' 처럼 일반화하세요",
            ))
        if not exp.verified:
            report.add(Finding(
                "REF", WARN, question.id,
                f"사실 확인이 끝나지 않은 경험입니다(verified: false): {exp_id}",
            ))
    if not answer.used:
        report.add(Finding(
            "REF", INFO, question.id,
            "used(근거 경험 id)가 비어 있습니다",
            hint="어느 경험에 근거한 답변인지 적어두면 수치 검증과 면접 준비가 쉬워집니다",
        ))


# --------------------------------------------------------------------------
# 실행
# --------------------------------------------------------------------------

def lint_answer(answer: Answer, question: Question, note: CareerNote,
                company: CompanyProfile, report: LintReport) -> None:
    check_length(answer, question, report)
    check_subtitle(answer, question, company, report)
    check_numbers(answer, question, note, company, report)
    check_cliches(answer, question, report)
    check_overtime(answer, question, report)
    check_weakness(answer, question, company, note, report)
    check_company_facts(answer, question, company, report)
    check_motivation_balance(answer, question, company, report)
    check_sentences(answer, question, report)
    check_evidence_links(answer, question, note, report)


def lint_draft(draft, note: CareerNote, company: CompanyProfile) -> LintReport:
    report = LintReport()
    answered = {a.id for a in draft.answers}

    for question in company.questions:
        answer = draft.answer(question.id)
        if answer is None or not answer.body:
            report.add(Finding(
                "MISSING", ERROR, question.id,
                f"문항 {question.id} 답변이 없습니다",
                evidence=truncate(question.text, 50),
            ))
            continue
        lint_answer(answer, question, note, company, report)

    for extra_id in answered - {q.id for q in company.questions}:
        report.add(Finding(
            "EXTRA", WARN, extra_id,
            f"회사 문항 목록에 없는 답변입니다: {extra_id}",
        ))
    return report
