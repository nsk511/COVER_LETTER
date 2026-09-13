"""문항별 설계(개요)와 LLM 프롬프트 생성.

이 도구는 초안을 '짓지' 않는다. 경력 노트에 있는 재료로 구조를 짜고,
그 구조와 재료를 그대로 담은 프롬프트를 만든다. 프롬프트에는 지어내기
금지 규칙이 항상 함께 들어간다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .matching import ExperienceMatch, recommend, resolve_axes
from .models import CareerNote, CompanyProfile, Experience, Question

# 문항 유형별 문단 구성과 분량 배분(%)
PARAGRAPH_PLANS: dict[str, list[tuple[str, int, str]]] = {
    "motivation": [
        ("회사 방향성", 15, "출처가 확인된 최신 사실 1개만. 연혁·철학 나열 금지"),
        ("내 경험과의 연결", 40, "그 방향성과 겹치는 본인의 실제 경험 — 여기가 본문의 중심"),
        ("직무 적합성", 25, "지원 직무에서 지금 할 수 있는 일. 없는 경험은 '배우고 싶다'로만"),
        ("입사 후 목표", 20, "1~3년 내 구체적 목표 1개. 추상적 각오 금지"),
    ],
    "achievement": [
        ("상황과 과제", 20, "무엇이 문제였는지 + 내가 맡은 범위"),
        ("행동과 판단 근거", 45, "'왜 그 방법이 가능했는가'의 도메인 이유까지. 클리셰 금지"),
        ("결과", 20, "경력 노트 metrics 의 숫자만"),
        ("배운 점과 적용", 15, "지원 직무에서 어떻게 쓸 것인지 한 문장"),
    ],
    "challenge": [
        ("직면한 어려움", 25, "난이도가 드러나는 조건(제약, 기한, 검증 기준)"),
        ("시도와 과정", 45, "실패한 시도가 있다면 함께. 과정이 곧 역량 증거"),
        ("결과", 20, "실제 수치"),
        ("배운 점", 10, ""),
    ],
    "collaboration": [
        ("상황과 이견", 25, "누구와 무엇이 달랐는지"),
        ("내 역할과 설득 근거", 40, "'우리'가 아니라 '내가' 한 일을 동사로"),
        ("결과", 20, "합의된 내용과 성과"),
        ("배운 점", 15, ""),
    ],
    "strength_weakness": [
        ("강점 + 근거 경험", 45, "강점 선언 1문장 + 증명 경험 1개"),
        ("보완이 필요한 점", 35, "치명적 약점 금지. '~에 집중하다 보니 ~에 더 노력이 필요했다'"),
        ("같은 강점으로 보완 중", 20, "약점을 강점으로 극복하는 구조 + 현재 실천 중인 방법"),
    ],
    "growth": [
        ("배움의 계기", 20, ""),
        ("학습과 적용", 50, "무엇을 어떻게 배워 업무에 적용했는지"),
        ("결과", 20, "실제 변화"),
        ("앞으로", 10, ""),
    ],
    "free": [
        ("핵심 주장", 20, ""),
        ("근거 경험", 50, ""),
        ("결과", 20, ""),
        ("연결", 10, ""),
    ],
}

WRITING_RULES = [
    "경력 노트에 없는 경험·수치·어려움은 절대 만들어내지 않는다. 재료가 부족하면 채우지 말고 '추가 확인 필요'로 남긴다.",
    "기술적 경험을 '최적화했다', '불필요한 로직을 제거했다' 같은 클리셰로 뭉뚱그리지 않는다. 왜 그 방법이 가능했는지 도메인 이유를 쓴다.",
    "확인되지 않은 회사 정보는 쓰지 않는다. research 에 checked: true 인 항목만 인용한다.",
    "약점은 지원 직무 핵심역량과 직결되는 치명적 약점으로 쓰지 않는다. 같은 강점으로 보완 중인 구조로 연결한다.",
    "'야근', '퇴근 후' 등 근무 외 시간을 강조하지 않는다. 무엇을 분석해 무엇을 바꿨는지로 쓴다.",
    "소제목은 [방법(how)] + [결과(result)] 공식. 특정 팀에만 해당하는 좁은 표현은 피한다.",
    "문장은 한 문장에 한 가지만. 95자를 넘기지 않는다.",
    "글자수 제한을 반드시 지킨다(공백포함 기준 90% 내외 권장).",
]


@dataclass
class ParagraphSlot:
    name: str
    share: int
    chars: int
    guide: str


@dataclass
class QuestionPlan:
    question: Question
    paragraphs: list[ParagraphSlot] = field(default_factory=list)
    picks: list[tuple[ExperienceMatch, int, list[str]]] = field(default_factory=list)
    subtitle_candidates: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def target_chars(self) -> int:
        limit = self.question.limit
        if limit.max and limit.min:
            return int((limit.max + limit.min) / 2)
        if limit.max:
            return int(limit.max * 0.92)
        if limit.min:
            return int(limit.min * 1.1)
        return 800

    def primary(self) -> Experience | None:
        return self.picks[0][0].experience if self.picks else None


def _subtitle_candidates(exp: Experience | None, question: Question,
                         company: CompanyProfile) -> list[str]:
    """[방법] + [결과] 공식으로 소제목 후보를 만든다 (초안 재료, 그대로 쓰지 말 것)."""
    if exp is None:
        return []
    metric = exp.metrics[0] if exp.metrics else None
    result = ""
    if metric:
        if metric.delta:
            result = metric.delta
        elif metric.before and metric.after:
            result = f"{metric.name} {metric.before}→{metric.after}"
        else:
            result = f"{metric.name} {metric.after}".strip()
    result = result or exp.result[:20]

    method = exp.title.split()[0] if exp.title else exp.role
    candidates = []
    if question.type == "motivation":
        theme = company.name or "회사"
        candidates.append(f"{exp.domain[0] if exp.domain else '현장'}에서 확인한 기준, {theme}에서 잇겠습니다")
    if result and exp.insight:
        head = exp.insight.split(".")[0].strip()
        if len(head) > 28:                       # 단어 중간에서 잘리지 않게
            head = head[:28].rsplit(" ", 1)[0]
        candidates.append(f"{head}, {result}")
    if result and method:
        candidates.append(f"{method}(으)로 {result}")
    if exp.title:
        candidates.append(exp.title)
    return [c.strip() for c in candidates if c.strip()][:4]


def plan_question(question: Question, note: CareerNote,
                  company: CompanyProfile) -> QuestionPlan:
    plan = QuestionPlan(question=question)
    layout = PARAGRAPH_PLANS.get(question.type, PARAGRAPH_PLANS["free"])
    target = plan.target_chars
    plan.paragraphs = [
        ParagraphSlot(name, share, round(target * share / 100), guide)
        for name, share, guide in layout
    ]
    plan.picks = recommend(note, company, question, limit=3)
    primary = plan.primary()
    plan.subtitle_candidates = _subtitle_candidates(primary, question, company)

    if not plan.picks:
        plan.warnings.append("추천할 경험이 없습니다. 경력 노트를 먼저 채우세요.")
    elif plan.picks[0][1] < 10:
        plan.warnings.append("이 문항에 뚜렷하게 맞는 경험이 없습니다. 경험을 추가하거나 use: 로 직접 지정하세요.")
    if primary and primary.star_gaps():
        plan.warnings.append(
            f"주 경험 {primary.id} 의 {', '.join(primary.star_gaps())} 이(가) 비어 있습니다."
        )
    if question.type == "motivation" and not company.usable_research():
        plan.warnings.append(
            "확인된 회사 리서치(source + checked: true)가 없습니다. 지원동기는 리서치 없이 쓰지 않습니다."
        )
    if not question.limit.max and not question.limit.min:
        plan.warnings.append("글자수 제한이 입력되지 않았습니다. 공고 원문을 확인하세요.")
    return plan


def plan_all(note: CareerNote, company: CompanyProfile) -> list[QuestionPlan]:
    return [plan_question(q, note, company) for q in company.questions]


# --------------------------------------------------------------------------
# LLM 프롬프트
# --------------------------------------------------------------------------

def _experience_block(exp: Experience) -> str:
    lines = [f"### 경험 [{exp.id}] {exp.title}"]
    fields = [
        ("기간", exp.period), ("소속", exp.org), ("역할", exp.role),
        ("분야", ", ".join(exp.domain)),
        ("상황", exp.situation), ("과제", exp.task), ("행동", exp.action),
        ("결과", exp.result), ("도메인 통찰", exp.insight),
        ("어려웠던 점", exp.difficulty), ("협업", exp.collaboration),
        ("배운 점", exp.lesson),
    ]
    for label, value in fields:
        if value:
            lines.append(f"- {label}: {value}")
    for metric in exp.metrics:
        lines.append(f"- 수치: {metric.as_text()}")
    if exp.confidential:
        lines.append("- ⚠ 대외비: 고객사명 등은 일반화해서 표현할 것")
    return "\n".join(lines)


def system_prompt() -> str:
    rules = "\n".join(f"{i + 1}. {rule}" for i, rule in enumerate(WRITING_RULES))
    return (
        "당신은 한국 대기업/금융권 자기소개서를 다뤄온 채용 컨설턴트입니다.\n"
        "지원자가 제공한 '경력 노트'에 적힌 사실만으로 자소서를 씁니다.\n\n"
        f"[절대 규칙]\n{rules}\n\n"
        "재료가 부족해 문단을 채울 수 없으면, 문장을 지어내지 말고 그 자리에 "
        "'⚠ 확인 필요: (무엇을 물어봐야 하는지)' 를 남기세요."
    )


def question_prompt(plan: QuestionPlan, note: CareerNote, company: CompanyProfile) -> str:
    question = plan.question
    axes = resolve_axes(company)
    parts: list[str] = []

    parts.append("## 지원 정보")
    parts.append(f"- 회사: {company.name}")
    parts.append(f"- 직무: {company.position}" + (f" ({company.team})" if company.team else ""))
    if company.core_competencies:
        parts.append(f"- 직무 핵심역량: {', '.join(company.core_competencies)}")
    if axes:
        parts.append("- 인재상: " + ", ".join(f"{a.source} → {a.axis}" for a in axes))
    usable = company.usable_research()
    if usable:
        parts.append("- 인용 가능한 회사 사실(확인 완료):")
        for item in usable:
            parts.append(f"  · {item.claim} (출처: {item.source}, {item.date})")
    else:
        parts.append("- 인용 가능한 회사 사실: 없음 → 회사 관련 사실 주장을 쓰지 말 것")

    parts.append("\n## 문항")
    parts.append(f"{question.text}")
    parts.append(f"- 글자수: {question.limit.describe()} (목표 {plan.target_chars}자 내외)")
    if question.hint:
        parts.append(f"- 참고: {question.hint}")

    parts.append("\n## 문단 구성 (이 배분을 지킬 것)")
    for slot in plan.paragraphs:
        guide = f" — {slot.guide}" if slot.guide else ""
        parts.append(f"- {slot.name}: 약 {slot.chars}자({slot.share}%){guide}")

    parts.append("\n## 쓸 수 있는 재료 (여기 없는 내용은 쓰지 말 것)")
    for match, score, reasons in plan.picks:
        parts.append(_experience_block(match.experience))
        parts.append(f"  (추천 점수 {score} — {'; '.join(reasons[:3])})")

    if question.type == "strength_weakness":
        if note.strengths:
            parts.append("\n### 강점(지원자가 실제로 말한 것)")
            for trait in note.strengths:
                parts.append(f"- {trait.label}: {trait.detail}")
        if note.weaknesses:
            parts.append("\n### 약점(지원자가 실제로 말한 것 — 여기 없는 약점 금지)")
            for trait in note.weaknesses:
                parts.append(
                    f"- {trait.label}: {trait.detail} / 개선: {trait.improving or '—'}"
                    f" / 보완 강점: {trait.offset_by or '—'}"
                )
    if question.type == "motivation" and note.values:
        parts.append("\n### 지원자의 가치관")
        parts.extend(f"- {v}" for v in note.values)

    if plan.subtitle_candidates:
        parts.append("\n## 소제목 후보 (그대로 쓰지 말고 다듬을 것)")
        parts.extend(f"- {c}" for c in plan.subtitle_candidates)

    parts.append("\n## 출력 형식")
    parts.append("소제목: [방법 + 결과 형태의 한 줄]")
    parts.append("본문: (문단 구성에 맞춰 작성, 줄바꿈으로 문단 구분)")
    parts.append("확인필요: (지어내지 않고 비워둔 부분이 있으면 목록으로, 없으면 '없음')")
    parts.append(f"\n작성 후 글자수를 세어 {question.limit.describe()} 범위인지 직접 확인하고 표기하세요.")

    return "\n".join(parts)
