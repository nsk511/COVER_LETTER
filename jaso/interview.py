"""자소서에서 면접 질문을 역산한다.

면접관은 자소서에 쓰인 문장을 근거로 묻는다. 그래서 질문은 '만들어내는' 것이
아니라 초안에서 '추출하는' 것이다. 수치·도메인 용어·협업·약점 서술은 각각
정해진 형태의 꼬리질문을 부른다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .loader import domain_terms
from .matching import resolve_axes
from .models import Answer, CareerNote, CompanyProfile, Draft, Experience, Question
from .textutil import contains_any, extract_numbers, particle, split_sentences, truncate

HIGH, MEDIUM, LOW = "높음", "보통", "낮음"


@dataclass
class InterviewQuestion:
    category: str
    question: str
    source: str = ""        # 어느 문장/경험에서 나온 질문인지
    prep: str = ""          # 답변 준비 뼈대
    risk: str = MEDIUM      # 준비가 안 되면 위험한 정도
    question_id: str = ""


@dataclass
class InterviewPack:
    questions: list[InterviewQuestion] = field(default_factory=list)
    scripts: list[tuple[Experience, str]] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)

    def by_category(self) -> dict[str, list[InterviewQuestion]]:
        grouped: dict[str, list[InterviewQuestion]] = {}
        for item in self.questions:
            grouped.setdefault(item.category, []).append(item)
        return grouped


_COLLAB_MARKERS = ["협업", "설득", "합의", "조율", "함께", "팀", "부서", "현업", "회의", "공유"]
_CONFLICT_MARKERS = ["반대", "이견", "갈등", "충돌", "거절", "설득"]
_LEAD_MARKERS = ["주도", "제안", "이끌", "총괄", "리드", "먼저"]


def _numeric_probe(sentence: str, tokens: list[str], qid: str) -> InterviewQuestion:
    joined = ", ".join(tokens[:3])
    return InterviewQuestion(
        category="수치 검증",
        question=f"「{joined}」는 어떻게 측정한 숫자인가요? 계산 기준과 대상 기간을 설명해 주세요.",
        source=truncate(sentence, 60),
        prep="① 무엇을 기준으로 쟀는지 ② 비교 대상(before)이 무엇인지 ③ 그 숫자를 확인한 방법(쿼리/검증표)",
        risk=HIGH,
        question_id=qid,
    )


def _term_probe(term: str, sentence: str, qid: str) -> InterviewQuestion:
    return InterviewQuestion(
        category="도메인 지식",
        question=f"자소서에 쓴 '{term}'{particle(term, '이', '가')} 무엇인지, 업무에서 어떤 의미였는지 설명해 주세요.",
        source=truncate(sentence, 60),
        prep=f"{term}의 정의 한 문장 + 본인 업무에서의 역할 한 문장 + 실제로 다뤄본 사례 한 문장",
        risk=HIGH,
        question_id=qid,
    )


def probe_answer(answer: Answer, question: Question, note: CareerNote,
                 company: CompanyProfile) -> list[InterviewQuestion]:
    """답변 한 개에서 나올 수 있는 꼬리질문을 뽑는다."""
    results: list[InterviewQuestion] = []
    terms = domain_terms()
    seen_terms: set[str] = set()
    text = answer.full_text()

    for sentence in split_sentences(text):
        numbers = extract_numbers(sentence)
        if numbers:
            results.append(_numeric_probe(sentence, numbers, question.id))

        for term in contains_any(sentence, terms):
            if term in seen_terms:
                continue
            seen_terms.add(term)
            results.append(_term_probe(term, sentence, question.id))

        if contains_any(sentence, _CONFLICT_MARKERS):
            results.append(InterviewQuestion(
                category="협업·갈등",
                question="반대한 사람은 누구였고, 무엇을 근거로 설득했나요? 끝내 합의가 안 됐다면 어떻게 했을까요?",
                source=truncate(sentence, 60),
                prep="상대의 입장 한 문장 → 내가 제시한 근거(데이터/사례) → 최종 합의안 → 이후 관계",
                risk=HIGH,
                question_id=question.id,
            ))
        elif contains_any(sentence, _COLLAB_MARKERS):
            results.append(InterviewQuestion(
                category="협업·갈등",
                question="그 협업에서 본인이 직접 한 일과 다른 사람이 한 일을 나눠서 말해 주세요.",
                source=truncate(sentence, 60),
                prep="내 역할(동사로) / 상대 역할 / 내가 없었으면 달라졌을 결과",
                risk=MEDIUM,
                question_id=question.id,
            ))

        if contains_any(sentence, _LEAD_MARKERS):
            results.append(InterviewQuestion(
                category="주도성",
                question="그 일을 먼저 제안한 이유는 무엇이었고, 제안 전에 무엇을 확인했나요?",
                source=truncate(sentence, 60),
                prep="문제를 인지한 계기 → 사전 확인한 근거 → 제안 방식(누구에게, 어떤 형태로)",
                risk=MEDIUM,
                question_id=question.id,
            ))

    if question.type == "motivation":
        results.append(InterviewQuestion(
            category="지원동기",
            question=f"왜 다른 회사가 아니라 {company.name or '저희 회사'}인가요? 경쟁사와 비교해서 말해 주세요.",
            prep="회사 방향성 1개(출처 확인된 것) → 내 경험/가치관과 겹치는 지점 → 입사 후 하고 싶은 일 1개",
            risk=HIGH,
            question_id=question.id,
        ))
        results.append(InterviewQuestion(
            category="지원동기",
            question=f"{company.position or '이 직무'}에서 입사 1년 차에 무엇을 할 수 있다고 보나요?",
            prep="지금 할 수 있는 것(경험 기반) / 배워야 하는 것 / 그것을 배우는 방법",
            risk=MEDIUM,
            question_id=question.id,
        ))

    if question.type == "strength_weakness":
        results.append(InterviewQuestion(
            category="약점",
            question="그 약점 때문에 실제로 문제가 생긴 적이 있나요? 그때 어떻게 수습했나요?",
            prep="작은 실제 사례 → 즉시 한 조치 → 이후 바꾼 습관(지금도 하고 있는 것)",
            risk=HIGH,
            question_id=question.id,
        ))
        results.append(InterviewQuestion(
            category="약점",
            question="그 점이 이 직무 수행에 지장을 준다고 보진 않나요?",
            prep="직무 핵심업무와 약점이 겹치지 않는 이유 + 이미 보완하고 있는 근거 경험",
            risk=HIGH,
            question_id=question.id,
        ))

    return results


def axis_questions(company: CompanyProfile) -> list[InterviewQuestion]:
    """회사 인재상에서 나오는 기본 질문."""
    results = []
    for axis in resolve_axes(company):
        for probe in axis.probes:
            results.append(InterviewQuestion(
                category=f"인재상 · {axis.axis}",
                question=probe,
                source=f"인재상 원문: {axis.source}",
                prep="해당 축을 뒷받침하는 경험 1개를 STAR로 60초 분량 준비",
                risk=HIGH if not axis.mapped else MEDIUM,
            ))
    return results


def job_questions(company: CompanyProfile) -> list[InterviewQuestion]:
    results = [InterviewQuestion(
        category="직무 이해",
        question=f"{company.position or '이 직무'}에서 가장 어려운 점이 무엇이라고 생각하나요?",
        prep="업무 흐름 이해를 보여주는 어려움 1개 + 본인 경험에서 비슷하게 겪은 지점",
        risk=HIGH,
    )]
    for competency in company.core_competencies[:5]:
        results.append(InterviewQuestion(
            category="직무 이해",
            question=f"'{competency}' 관련해서 해본 일이 있다면 말해 주세요. 없다면 어떻게 준비하고 있나요?",
            prep="있으면 STAR 30초 / 없으면 '현재 경험 + 배우고 싶은 이유'로 과장 없이",
            risk=MEDIUM,
        ))
    return results


def script_for(experience: Experience) -> str:
    """경험 1건의 구술 답변 뼈대 (30초/60초)."""
    metrics = " · ".join(
        f"{m.name} {m.before}→{m.after}" if m.before and m.after
        else f"{m.name} {m.after or m.delta}".strip()
        for m in experience.metrics
    ) or "(정량 성과 미정리)"

    lines = [
        f"■ {experience.label()}  [{experience.period}]",
        "",
        "· 30초 버전",
        f"  {experience.situation or '(상황 미작성)'} 상황에서, "
        f"{experience.task or '(과제 미작성)'} 를 맡아 "
        f"{truncate(experience.action, 60) or '(행동 미작성)'} 했습니다. "
        f"그 결과 {metrics} 였습니다.",
        "",
        "· 60초 버전 (꼬리질문 대비)",
        f"  ① 상황: {experience.situation or '—'}",
        f"  ② 과제: {experience.task or '—'}",
        f"  ③ 행동: {experience.action or '—'}",
        f"  ④ 결과: {experience.result or '—'}  ({metrics})",
        f"  ⑤ 왜 그 방법이 가능했나: {experience.insight or '⚠ 미작성 — 여기가 가장 많이 물어봅니다'}",
        f"  ⑥ 어려웠던 점: {experience.difficulty or '—'}",
        f"  ⑦ 배운 점: {experience.lesson or '—'}",
    ]
    return "\n".join(lines)


def build_pack(draft: Draft, note: CareerNote, company: CompanyProfile) -> InterviewPack:
    pack = InterviewPack()
    pack.questions.extend(axis_questions(company))
    pack.questions.extend(job_questions(company))

    used_ids: list[str] = []
    for question in company.questions:
        answer = draft.answer(question.id)
        if answer is None or not answer.body:
            continue
        pack.questions.extend(probe_answer(answer, question, note, company))
        used_ids.extend(answer.used)

    targets = [note.by_id(i) for i in dict.fromkeys(used_ids)]
    targets = [t for t in targets if t is not None]
    if not targets:
        targets = note.experiences
    for exp in targets:
        pack.scripts.append((exp, script_for(exp)))
        gaps = exp.star_gaps()
        if gaps:
            pack.gaps.append(f"{exp.id} ({exp.label()}): {', '.join(gaps)} 미작성")

    # 중복 질문 제거 (같은 질문 문장은 한 번만)
    seen: set[str] = set()
    unique: list[InterviewQuestion] = []
    for item in pack.questions:
        if item.question in seen:
            continue
        seen.add(item.question)
        unique.append(item)
    order = {HIGH: 0, MEDIUM: 1, LOW: 2}
    unique.sort(key=lambda q: (order[q.risk], q.category))
    pack.questions = unique
    return pack
