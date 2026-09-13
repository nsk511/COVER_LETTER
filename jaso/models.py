"""자소서 작성에 사용하는 데이터 모델.

모든 모델은 YAML에서 읽어온 dict를 그대로 감싸는 얇은 dataclass다.
알 수 없는 키는 ``extra`` 에 보관해 두므로, 사용자가 자기 방식대로
필드를 추가해도 정보가 사라지지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _as_list(value: Any) -> list[Any]:
    """스칼라/None/리스트를 모두 리스트로 정규화한다."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [v for v in value if v is not None]
    return [value]


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value)


def _known(data: dict[str, Any], keys: set[str]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if k not in keys}


# --------------------------------------------------------------------------
# 경력 노트 (career note)
# --------------------------------------------------------------------------

@dataclass
class Metric:
    """경험의 정량 성과. 자소서에 쓸 수 있는 숫자는 여기 있는 것만 인정한다."""

    name: str = ""
    before: str = ""
    after: str = ""
    delta: str = ""
    note: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> "Metric":
        if isinstance(data, str):
            return cls(name=data.strip())
        data = data or {}
        return cls(
            name=_as_str(data.get("name")),
            before=_as_str(data.get("before")),
            after=_as_str(data.get("after")),
            delta=_as_str(data.get("delta")),
            note=_as_str(data.get("note")),
        )

    def as_text(self) -> str:
        parts = [p for p in (self.name, self.before, self.after, self.delta, self.note) if p]
        return " ".join(parts)


@dataclass
class Experience:
    """STAR 구조로 정리한 실제 경험 한 건."""

    id: str
    title: str = ""
    period: str = ""
    org: str = ""
    role: str = ""
    domain: list[str] = field(default_factory=list)
    situation: str = ""
    task: str = ""
    action: str = ""
    result: str = ""
    insight: str = ""          # 도메인 통찰 — 꼬리질문 방어의 핵심
    difficulty: str = ""
    collaboration: str = ""
    lesson: str = ""
    metrics: list[Metric] = field(default_factory=list)
    axes: list[str] = field(default_factory=list)   # 사용자가 직접 지정한 역량축
    keywords: list[str] = field(default_factory=list)
    confidential: bool = False
    verified: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    _KEYS = {
        "id", "title", "period", "org", "role", "domain", "situation", "task",
        "action", "result", "insight", "difficulty", "collaboration", "lesson",
        "metrics", "axes", "keywords", "confidential", "verified",
    }

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int = 0) -> "Experience":
        data = data or {}
        exp_id = _as_str(data.get("id")) or f"exp-{index + 1:02d}"
        return cls(
            id=exp_id,
            title=_as_str(data.get("title")),
            period=_as_str(data.get("period")),
            org=_as_str(data.get("org")),
            role=_as_str(data.get("role")),
            domain=[_as_str(v) for v in _as_list(data.get("domain"))],
            situation=_as_str(data.get("situation")),
            task=_as_str(data.get("task")),
            action=_as_str(data.get("action")),
            result=_as_str(data.get("result")),
            insight=_as_str(data.get("insight")),
            difficulty=_as_str(data.get("difficulty")),
            collaboration=_as_str(data.get("collaboration")),
            lesson=_as_str(data.get("lesson")),
            metrics=[Metric.from_dict(m) for m in _as_list(data.get("metrics"))],
            axes=[_as_str(v) for v in _as_list(data.get("axes"))],
            keywords=[_as_str(v) for v in _as_list(data.get("keywords"))],
            confidential=bool(data.get("confidential", False)),
            verified=bool(data.get("verified", True)),
            extra=_known(data, cls._KEYS),
        )

    def searchable_text(self) -> str:
        """매칭용 전체 텍스트."""
        chunks = [
            self.title, self.role, self.situation, self.task, self.action,
            self.result, self.insight, self.difficulty, self.collaboration,
            self.lesson,
            " ".join(self.domain), " ".join(self.keywords), " ".join(self.axes),
            " ".join(m.as_text() for m in self.metrics),
        ]
        return "\n".join(c for c in chunks if c)

    def star_gaps(self) -> list[str]:
        """STAR 중 비어 있는 칸 — 면접에서 바로 뚫리는 지점."""
        gaps = []
        for label, value in (
            ("상황(situation)", self.situation),
            ("과제(task)", self.task),
            ("행동(action)", self.action),
            ("결과(result)", self.result),
        ):
            if not value:
                gaps.append(label)
        if not self.metrics:
            gaps.append("정량 성과(metrics)")
        if not self.insight:
            gaps.append("도메인 통찰(insight)")
        return gaps

    def label(self) -> str:
        return self.title or self.id


@dataclass
class Trait:
    """강점 또는 약점."""

    label: str = ""
    detail: str = ""
    evidence: list[str] = field(default_factory=list)   # experience id 참조
    improving: str = ""        # 약점: 개선하고 있는 방식 (실제 사실만)
    offset_by: str = ""        # 약점: 어떤 강점으로 보완하는지

    @classmethod
    def from_dict(cls, data: Any) -> "Trait":
        if isinstance(data, str):
            return cls(label=data.strip())
        data = data or {}
        return cls(
            label=_as_str(data.get("label")),
            detail=_as_str(data.get("detail")),
            evidence=[_as_str(v) for v in _as_list(data.get("evidence"))],
            improving=_as_str(data.get("improving")),
            offset_by=_as_str(data.get("offset_by")),
        )


@dataclass
class CareerNote:
    """지원자의 실제 경력 전체. 자소서 내용의 유일한 원천(source of truth)."""

    owner: dict[str, Any] = field(default_factory=dict)
    values: list[str] = field(default_factory=list)
    strengths: list[Trait] = field(default_factory=list)
    weaknesses: list[Trait] = field(default_factory=list)
    skills: list[dict[str, Any]] = field(default_factory=list)
    experiences: list[Experience] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    _KEYS = {"owner", "values", "strengths", "weaknesses", "skills", "experiences"}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CareerNote":
        data = data or {}
        owner = data.get("owner") or {}
        if isinstance(owner, str):
            owner = {"name": owner}
        return cls(
            owner=owner,
            values=[_as_str(v) for v in _as_list(data.get("values"))],
            strengths=[Trait.from_dict(t) for t in _as_list(data.get("strengths"))],
            weaknesses=[Trait.from_dict(t) for t in _as_list(data.get("weaknesses"))],
            skills=[s if isinstance(s, dict) else {"name": _as_str(s)}
                    for s in _as_list(data.get("skills"))],
            experiences=[Experience.from_dict(e, i)
                         for i, e in enumerate(_as_list(data.get("experiences")))],
            extra=_known(data, cls._KEYS),
        )

    def by_id(self, exp_id: str) -> Experience | None:
        for exp in self.experiences:
            if exp.id == exp_id:
                return exp
        return None

    def owner_name(self) -> str:
        return _as_str(self.owner.get("name")) or "지원자"

    def all_text(self) -> str:
        chunks = [e.searchable_text() for e in self.experiences]
        chunks += [f"{t.label} {t.detail} {t.improving}" for t in self.strengths]
        chunks += [f"{t.label} {t.detail} {t.improving}" for t in self.weaknesses]
        chunks += [str(s) for s in self.skills]
        chunks += self.values
        return "\n".join(c for c in chunks if c)


# --------------------------------------------------------------------------
# 회사 / 문항
# --------------------------------------------------------------------------

@dataclass
class Limit:
    """글자수 제한. count_mode 는 with_space / without_space."""

    min: int | None = None
    max: int | None = None
    count_mode: str = "with_space"

    @classmethod
    def from_dict(cls, data: Any) -> "Limit":
        if data is None:
            return cls()
        if isinstance(data, int):
            return cls(max=data)
        if isinstance(data, str):
            digits = "".join(ch for ch in data if ch.isdigit())
            return cls(max=int(digits) if digits else None)
        mode = _as_str(data.get("count_mode")) or "with_space"
        if mode not in ("with_space", "without_space"):
            mode = "with_space"
        return cls(
            min=data.get("min"),
            max=data.get("max"),
            count_mode=mode,
        )

    def describe(self) -> str:
        mode = "공백포함" if self.count_mode == "with_space" else "공백제외"
        if self.min and self.max:
            return f"{self.min}~{self.max}자({mode})"
        if self.max:
            return f"최대 {self.max}자({mode})"
        if self.min:
            return f"최소 {self.min}자({mode})"
        return "제한 없음"


@dataclass
class Question:
    """자소서 문항 한 개."""

    id: str
    text: str = ""
    type: str = "free"      # motivation/achievement/strength_weakness/collaboration/challenge/growth/free
    limit: Limit = field(default_factory=Limit)
    hint: str = ""
    use: list[str] = field(default_factory=list)     # 이 문항에 쓸 experience id (사용자 지정)

    _KEYS = {"id", "text", "type", "limit", "hint", "use"}

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int = 0) -> "Question":
        data = data or {}
        return cls(
            id=_as_str(data.get("id")) or f"q{index + 1}",
            text=_as_str(data.get("text")),
            type=_as_str(data.get("type")) or "free",
            limit=Limit.from_dict(data.get("limit")),
            hint=_as_str(data.get("hint")),
            use=[_as_str(v) for v in _as_list(data.get("use"))],
        )


@dataclass
class ResearchItem:
    """회사 리서치 한 줄. 출처 없는 주장은 자소서에 쓰지 않는다."""

    claim: str = ""
    source: str = ""
    date: str = ""
    checked: bool = False

    @classmethod
    def from_dict(cls, data: Any) -> "ResearchItem":
        if isinstance(data, str):
            return cls(claim=data.strip())
        data = data or {}
        return cls(
            claim=_as_str(data.get("claim")),
            source=_as_str(data.get("source")),
            date=_as_str(data.get("date")),
            checked=bool(data.get("checked", False)),
        )

    def is_usable(self) -> bool:
        return bool(self.claim and self.source and self.checked)


@dataclass
class CompanyProfile:
    """지원 회사 + 직무 + 문항."""

    name: str = ""
    position: str = ""
    team: str = ""
    apply_deadline: str = ""
    talent_profile: list[str] = field(default_factory=list)   # 인재상
    core_competencies: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    research: list[ResearchItem] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    tone: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    _KEYS = {
        "name", "position", "team", "apply_deadline", "talent_profile",
        "core_competencies", "keywords", "research", "questions", "tone",
    }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompanyProfile":
        data = data or {}
        company = data.get("company") if isinstance(data.get("company"), dict) else {}
        merged: dict[str, Any] = {**company}
        for key in ("questions", "research", "talent_profile", "core_competencies"):
            if key in data:
                merged[key] = data[key]
        return cls(
            name=_as_str(merged.get("name")),
            position=_as_str(merged.get("position")),
            team=_as_str(merged.get("team")),
            apply_deadline=_as_str(merged.get("apply_deadline")),
            talent_profile=[_as_str(v) for v in _as_list(merged.get("talent_profile"))],
            core_competencies=[_as_str(v) for v in _as_list(merged.get("core_competencies"))],
            keywords=[_as_str(v) for v in _as_list(merged.get("keywords"))],
            research=[ResearchItem.from_dict(r) for r in _as_list(merged.get("research"))],
            questions=[Question.from_dict(q, i)
                       for i, q in enumerate(_as_list(merged.get("questions")))],
            tone=_as_str(merged.get("tone")),
            extra=_known(merged, cls._KEYS),
        )

    def question(self, qid: str) -> Question | None:
        for q in self.questions:
            if q.id == qid:
                return q
        return None

    def role_label(self) -> str:
        parts = [p for p in (self.name, self.team, self.position) if p]
        return " ".join(parts)

    def usable_research(self) -> list[ResearchItem]:
        return [r for r in self.research if r.is_usable()]


# --------------------------------------------------------------------------
# 초안
# --------------------------------------------------------------------------

@dataclass
class Answer:
    """문항별 답변 초안."""

    id: str
    subtitle: str = ""
    body: str = ""
    used: list[str] = field(default_factory=list)   # 근거로 삼은 experience id
    note: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int = 0) -> "Answer":
        data = data or {}
        return cls(
            id=_as_str(data.get("id")) or f"q{index + 1}",
            subtitle=_as_str(data.get("subtitle")),
            body=_as_str(data.get("body")),
            used=[_as_str(v) for v in _as_list(data.get("used"))],
            note=_as_str(data.get("note")),
        )

    def full_text(self) -> str:
        """소제목 포함 전체 텍스트 (글자수 계산 기준)."""
        if self.subtitle:
            return f"[{self.subtitle}]\n{self.body}"
        return self.body


@dataclass
class Draft:
    answers: list[Answer] = field(default_factory=list)
    company: str = ""
    position: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Draft":
        data = data or {}
        return cls(
            answers=[Answer.from_dict(a, i)
                     for i, a in enumerate(_as_list(data.get("answers")))],
            company=_as_str(data.get("company")),
            position=_as_str(data.get("position")),
        )

    def answer(self, qid: str) -> Answer | None:
        for a in self.answers:
            if a.id == qid:
                return a
        return None
