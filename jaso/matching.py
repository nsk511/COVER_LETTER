"""인재상 ↔ 경험 매칭 엔진.

회사가 내건 인재상 문구를 표준 역량축으로 옮기고, 경력 노트의 각 경험이
그 축을 얼마나 뒷받침하는지 점수화한다. 여기서 나온 순위가 '어느 문항에
어느 경험을 쓸 것인가'의 근거가 된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .loader import talent_axes
from .models import CareerNote, CompanyProfile, Experience, Question
from .textutil import contains_any, strip_spaces

# 문항 유형별로 우선하는 역량축과 경험 필드
QUESTION_PROFILE: dict[str, dict[str, list[str]]] = {
    "motivation": {
        "axes": ["전문성", "고객중심", "도전·혁신"],
        "fields": ["insight", "result", "role"],
    },
    "achievement": {
        "axes": ["실행력·책임감", "전문성", "데이터·분석", "창의·문제해결"],
        "fields": ["result", "action", "metrics"],
    },
    "challenge": {
        "axes": ["도전·혁신", "창의·문제해결", "실행력·책임감"],
        "fields": ["difficulty", "action", "insight"],
    },
    "collaboration": {
        "axes": ["협업·소통", "고객중심", "리더십"],
        "fields": ["collaboration", "difficulty"],
    },
    "strength_weakness": {
        "axes": ["전문성", "정직·신뢰", "성장·학습"],
        "fields": ["insight", "lesson", "action"],
    },
    "growth": {
        "axes": ["성장·학습", "전문성"],
        "fields": ["lesson", "insight"],
    },
    "value_definition": {
        "axes": ["정직·신뢰", "실행력·책임감", "전문성"],
        "fields": ["insight", "action", "lesson"],
    },
    "opinion_experience": {
        "axes": ["협업·소통", "고객중심", "창의·문제해결"],
        "fields": ["collaboration", "difficulty", "action"],
    },
    "growth_story": {
        "axes": ["성장·학습", "실행력·책임감", "도전·혁신"],
        "fields": ["difficulty", "action", "lesson"],
    },
    "social_issue": {
        "axes": ["전문성", "데이터·분석"],
        "fields": ["insight"],
    },
    "strength": {
        "axes": ["전문성", "창의·문제해결", "실행력·책임감"],
        "fields": ["insight", "action", "result", "metrics"],
    },
    "free": {"axes": [], "fields": []},
}

DEFAULT_AXIS_SOURCE = "(인재상 미입력 — 표준 역량축 사용)"

PREFERRED_AXIS_WEIGHT = 3
EXPLICIT_AXIS_BONUS = 4
METRIC_BONUS = 2
INSIGHT_BONUS = 2
FIELD_BONUS = 2
CORE_COMPETENCY_WEIGHT = 3


@dataclass
class ResolvedAxis:
    """회사 인재상 문구 한 줄을 표준축으로 해석한 결과."""

    source: str            # 회사가 쓴 원문 (예: "도전하는 프로")
    axis: str              # 매핑된 표준축 이름 (없으면 source 그대로)
    signals: list[str] = field(default_factory=list)
    probes: list[str] = field(default_factory=list)
    mapped: bool = True    # 사전에서 찾았는지 여부


@dataclass
class ExperienceMatch:
    """경험 1건이 회사 요구에 얼마나 맞는지."""

    experience: Experience
    axis_scores: dict[str, int] = field(default_factory=dict)
    axis_hits: dict[str, list[str]] = field(default_factory=dict)
    job_fit: int = 0
    job_hits: list[str] = field(default_factory=list)
    bonuses: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(self.axis_scores.values()) + self.job_fit

    def top_axes(self, limit: int = 3) -> list[tuple[str, int]]:
        ranked = sorted(self.axis_scores.items(), key=lambda kv: (-kv[1], kv[0]))
        return [(name, score) for name, score in ranked if score > 0][:limit]

    def evidence(self) -> list[str]:
        """왜 이 경험이 뽑혔는지 사람이 읽을 수 있는 근거."""
        reasons = []
        for name, score in self.top_axes():
            hits = self.axis_hits.get(name, [])
            hint = f" ({', '.join(hits[:4])})" if hits else ""
            reasons.append(f"{name} {score}점{hint}")
        if self.job_hits:
            reasons.append(f"직무 키워드: {', '.join(self.job_hits[:4])}")
        reasons.extend(self.bonuses)
        return reasons


def _tokenize(text: str) -> list[str]:
    """인재상 문구를 매칭용 토큰으로 쪼갠다."""
    cleaned = "".join(ch if ch.isalnum() else " " for ch in text)
    return [tok for tok in cleaned.split() if len(tok) >= 2]


def resolve_axes(company: CompanyProfile) -> list[ResolvedAxis]:
    """회사 인재상 문구들을 표준 역량축으로 변환한다.

    사전에 없는 문구는 버리지 않고, 문구 자체를 축으로 삼아 토큰을 신호로 쓴다.
    """
    dictionary = talent_axes()
    resolved: list[ResolvedAxis] = []
    seen: set[str] = set()

    for phrase in company.talent_profile:
        if not phrase:
            continue
        flat = strip_spaces(phrase)
        # '신뢰와 소통'처럼 한 문구가 둘 이상의 축을 담는 경우가 흔하므로
        # 걸리는 축을 모두 반영한다.
        matched = [
            axis_name for axis_name, spec in dictionary.items()
            if contains_any(flat, [str(a) for a in (spec.get("aliases") or [])] + [axis_name])
        ]
        if matched:
            for axis_name in matched:
                if axis_name in seen:
                    # 같은 축에 걸리는 문구가 둘이면 원문만 덧붙인다.
                    for item in resolved:
                        if item.axis == axis_name and phrase not in item.source:
                            item.source = f"{item.source} / {phrase}"
                    continue
                seen.add(axis_name)
                spec = dictionary[axis_name]
                resolved.append(ResolvedAxis(
                    source=phrase,
                    axis=axis_name,
                    signals=[str(s) for s in (spec.get("signals") or [])],
                    probes=[str(p) for p in (spec.get("probes") or [])],
                    mapped=True,
                ))
        else:
            if phrase in seen:
                continue
            seen.add(phrase)
            resolved.append(ResolvedAxis(
                source=phrase,
                axis=phrase,
                signals=_tokenize(phrase),
                probes=[f"'{phrase}'에 해당하는 본인의 경험을 말해보세요."],
                mapped=False,
            ))

    if not resolved:
        # 인재상을 아직 모르는 회사도 많다. 그럴 때 축 점수를 0으로 두면
        # 문항 유형별 선호축이 통째로 죽어 추천이 무의미해지므로,
        # 표준 역량축 전체를 기본값으로 쓴다.
        resolved = [
            ResolvedAxis(
                source=DEFAULT_AXIS_SOURCE,
                axis=axis_name,
                signals=[str(x) for x in (spec.get("signals") or [])],
                probes=[str(x) for x in (spec.get("probes") or [])],
                mapped=True,
            )
            for axis_name, spec in dictionary.items()
        ]
    return resolved


def using_default_axes(company: CompanyProfile) -> bool:
    """인재상 미입력으로 표준 축을 대신 쓰고 있는지."""
    return not [p for p in company.talent_profile if p]


def score_experience(
    experience: Experience,
    axes: list[ResolvedAxis],
    company: CompanyProfile,
) -> ExperienceMatch:
    """경험 1건에 대한 축별 점수와 직무 적합도를 계산한다."""
    text = experience.searchable_text()
    match = ExperienceMatch(experience=experience)

    for axis in axes:
        hits = contains_any(text, axis.signals)
        score = len(hits)
        if contains_any(" ".join(experience.axes), [axis.axis]) or axis.axis in experience.axes:
            score += EXPLICIT_AXIS_BONUS
            hits = hits + ["직접 태깅"]
        match.axis_scores[axis.axis] = score
        match.axis_hits[axis.axis] = hits

    job_terms = company.core_competencies + company.keywords
    match.job_hits = contains_any(text, job_terms)
    match.job_fit = len(match.job_hits) * CORE_COMPETENCY_WEIGHT

    if experience.metrics:
        match.job_fit += METRIC_BONUS
        match.bonuses.append("정량 성과 있음")
    if experience.insight:
        match.job_fit += INSIGHT_BONUS
        match.bonuses.append("도메인 통찰 있음")
    if not experience.verified:
        match.bonuses.append("⚠ 사실 확인 필요(verified: false)")
    if experience.confidential:
        match.bonuses.append("⚠ 대외비 — 익명화 필요")

    return match


def match_all(note: CareerNote, company: CompanyProfile) -> list[ExperienceMatch]:
    """전체 경험을 총점 순으로 정렬해 돌려준다."""
    axes = resolve_axes(company)
    matches = [score_experience(exp, axes, company) for exp in note.experiences]
    matches.sort(key=lambda m: (-m.total, m.experience.id))
    return matches


def question_fit(match: ExperienceMatch, question: Question) -> tuple[int, list[str]]:
    """문항 유형까지 반영한 점수와 그 이유."""
    profile = QUESTION_PROFILE.get(question.type, QUESTION_PROFILE["free"])
    preferred = set(profile["axes"])
    reasons: list[str] = []

    # 모든 축을 같은 무게로 더하면 '내용이 많은 경험'이 문항과 무관하게 1등이 된다.
    # 문항이 요구하는 축에 가중치를 주어 관련성이 점수를 지배하게 한다.
    score = match.job_fit
    for axis_name, gained in match.axis_scores.items():
        if not gained:
            continue
        weight = PREFERRED_AXIS_WEIGHT if axis_name in preferred else 1
        score += gained * weight
        if axis_name in preferred:
            reasons.append(f"{profile.get('label', question.type)} 선호축 {axis_name} {gained}×{weight}")

    exp = match.experience
    for fname in profile["fields"]:
        value = exp.metrics if fname == "metrics" else getattr(exp, fname, "")
        if value:
            score += FIELD_BONUS
            reasons.append(f"{fname} 작성됨 +{FIELD_BONUS}")

    if question.text:
        hits = contains_any(exp.searchable_text(), _tokenize(question.text))
        if hits:
            score += len(hits)
            reasons.append(f"문항 키워드 일치: {', '.join(hits[:4])}")

    return score, reasons


def recommend(
    note: CareerNote,
    company: CompanyProfile,
    question: Question,
    limit: int = 3,
) -> list[tuple[ExperienceMatch, int, list[str]]]:
    """문항에 쓸 경험 추천. 사용자가 question.use 를 지정했으면 그것을 우선한다."""
    matches = match_all(note, company)
    scored = []
    for match in matches:
        score, reasons = question_fit(match, question)
        if question.use and match.experience.id in question.use:
            score += 100
            reasons.insert(0, "사용자 지정(use)")
        scored.append((match, score, reasons))
    scored.sort(key=lambda item: (-item[1], item[0].experience.id))
    return scored[:limit]


def coverage(note: CareerNote, company: CompanyProfile) -> dict[str, list[str]]:
    """인재상 축별로 뒷받침할 경험이 있는지 — 비어 있는 축이 곧 준비해야 할 숙제다."""
    axes = resolve_axes(company)
    result: dict[str, list[str]] = {}
    for axis in axes:
        supporting = []
        for exp in note.experiences:
            match = score_experience(exp, [axis], company)
            if match.axis_scores.get(axis.axis, 0) >= 2:
                supporting.append(exp.id)
        result[axis.axis] = supporting
    return result


# 어절 끝에 붙는 조사 — 긴 것부터 떼어낸다
_PARTICLES = (
    "에게서", "으로써", "으로서", "에서는", "이라는", "에서", "으로", "부터", "까지",
    "에게", "처럼", "보다", "마다", "이나", "라도", "이고", "과의", "와의", "의",
    "은", "는", "이", "가", "을", "를", "에", "로", "과", "와", "도", "만",
)
# 용언 활용형으로 끝나면 명사가 아니다
_VERB_TAILS = (
    "하는", "되는", "하여", "되어", "하고", "되고", "하기", "되기", "지고", "시키고",
    "이며", "으며", "하며", "되며", "이고", "리고", "지는", "되지", "하지", "받는",
    "찾기", "여기고", "다하여", "갖춘", "느껴", "이라", "이다",
    "될", "할", "됨", "함", "든", "친", "낸",
)


def _noun(token: str) -> str:
    """어절에서 조사를 떼어 명사에 가깝게 만든다 (형태소 분석기 없는 근사)."""
    for tail in _VERB_TAILS:
        if token.endswith(tail):
            return ""
    for particle in _PARTICLES:
        if len(token) > len(particle) + 1 and token.endswith(particle):
            return token[: -len(particle)]
    return token


# 인재상 문구에서 걸러낼 기능어 — 회사 고유어만 남기기 위한 최소한의 목록
_GENERIC_WORDS = {
    "인재", "위해", "노력", "하는", "바탕", "모든", "최고", "최선", "자세", "가치",
    "지속적으로", "끊임없이", "새로운", "항상", "열린", "마음", "다하여", "전체",
    "통해", "되기", "여기고", "처리하여", "받는", "찾기", "추구하는", "갖춘",
    "매사에", "있도록", "가지고", "우리", "회사", "사람", "분야", "업무", "조직",
    "정신", "의식", "능력", "역량", "경험", "생각", "대한", "또는", "그리고",
    "자신", "본인", "함께", "만드는", "중심", "관리", "그를", "등을", "등의",
    "전체", "성과", "제고", "극대화", "지속적", "미래지향적", "혁신적", "역동적",
    "열정적", "진취적", "프로다운", "최상", "가족",
}


def vocabulary_gap(note: CareerNote, company: CompanyProfile, limit: int = 14) -> list[str]:
    """회사가 쓰는 말 중 경력 노트에 한 번도 나오지 않는 단어.

    인재상에만 있고 내 글에는 없는 단어가 많다는 건, 회사가 중요하게 보는 영역에
    접점이 없다는 뜻이다. 억지로 끼워 넣으라는 신호가 아니라, 실제 접점이 있는지
    다시 떠올려 보라는 신호다.
    """
    note_text = strip_spaces(note.all_text()).lower()
    seen: set[str] = set()
    missing: list[str] = []
    for phrase in company.talent_profile:
        for raw in _tokenize(phrase):
            token = _noun(raw)
            key = token.lower()
            if not token or len(token) < 2 or key in seen or token in _GENERIC_WORDS:
                continue
            seen.add(key)
            if key not in note_text:
                missing.append(token)
    return missing[:limit]
