"""한국어 자소서용 텍스트 유틸 — 글자수, 문장 분해, 숫자 추출."""

from __future__ import annotations

import re
import unicodedata

# 숫자 + 뒤따르는 단위(원/건/%/분/년/회차 등)를 한 덩어리로 잡는다.
_NUMBER_RE = re.compile(
    r"(?<![\w가-힣])"
    r"(\d[\d,]*(?:\.\d+)?)"
    r"\s*"
    r"(%|퍼센트|배|억|만|천|원|건|명|개|년|개월|주|일|시간|분|초|회차|회|차|위|점|급|학기|세트|번|종|가지|kg|km|MB|GB|TB)?"
)

_SENT_END_RE = re.compile(r"(?<=[.!?])\s+|(?<=다\.)\s*|\n+")

_WS_RE = re.compile(r"\s+")


def normalize_newlines(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def count_chars(text: str) -> tuple[int, int]:
    """(공백포함, 공백제외) 글자수를 반환한다.

    공백포함은 줄바꿈을 1자로 계산한다(대부분의 채용 시스템과 동일).
    공백제외는 모든 공백 문자를 뺀 길이다.
    """
    text = normalize_newlines(text)
    with_space = len(text)
    without_space = len(_WS_RE.sub("", text))
    return with_space, without_space


def count_for_mode(text: str, mode: str) -> int:
    with_space, without_space = count_chars(text)
    return without_space if mode == "without_space" else with_space


def split_sentences(text: str) -> list[str]:
    """한국어 문장 단위 분해. 완벽한 파서가 아니라 검증용 휴리스틱이다."""
    text = normalize_newlines(text).strip()
    if not text:
        return []
    raw = _SENT_END_RE.split(text)
    return [s.strip() for s in raw if s and s.strip()]


def strip_spaces(text: str) -> str:
    return _WS_RE.sub("", text or "")


def extract_numbers(text: str) -> list[str]:
    """텍스트에서 '90분', '78%', '2025년' 같은 수치 토큰을 뽑아낸다.

    지어낸 수치를 잡아내기 위한 용도라, 단위가 붙으면 단위까지 함께 돌려준다.
    """
    found: list[str] = []
    for match in _NUMBER_RE.finditer(normalize_newlines(text)):
        number, unit = match.group(1), match.group(2) or ""
        token = f"{number}{unit}"
        if token not in found:
            found.append(token)
    return found


def canonical_number(token: str) -> str:
    """'1,200 건' → '1200건' 처럼 비교 가능한 형태로 정규화."""
    token = unicodedata.normalize("NFKC", token or "")
    token = token.replace(",", "")
    token = _WS_RE.sub("", token)
    token = token.replace("퍼센트", "%")
    return token.lower()


def number_only(token: str) -> str:
    """단위를 뗀 숫자 부분만."""
    match = re.match(r"[\d.]+", canonical_number(token))
    return match.group(0).rstrip(".") if match else ""


def contains_any(text: str, needles: list[str]) -> list[str]:
    """text 안에 등장하는 needle 목록을 반환 (공백 무시 비교)."""
    flat = strip_spaces(text).lower()
    hits = []
    for needle in needles:
        key = strip_spaces(needle).lower()
        if key and key in flat:
            hits.append(needle)
    return hits


def truncate(text: str, length: int = 40) -> str:
    text = _WS_RE.sub(" ", (text or "").strip())
    if len(text) <= length:
        return text
    return text[: length - 1] + "…"


def ratio(part: int, total: int) -> float:
    return (part / total) if total else 0.0


def has_final_consonant(word: str) -> bool | None:
    """마지막 글자에 받침이 있는지. 한글이 아니면 None."""
    if not word:
        return None
    last = word[-1]
    if not ("가" <= last <= "힣"):
        return None
    return (ord(last) - 0xAC00) % 28 != 0


def particle(word: str, with_final: str, without_final: str) -> str:
    """받침에 맞는 조사만 돌려준다. particle('쿼리', '이', '가') → '가'"""
    final = has_final_consonant(word)
    if final is None:                 # 영문/숫자로 끝나면 병기해서 안전하게
        return f"{with_final}({without_final})"
    return with_final if final else without_final


def josa(word: str, with_final: str, without_final: str) -> str:
    """받침에 맞는 조사를 붙인다. josa('쿼리', '이', '가') → '쿼리가'"""
    return f"{word}{particle(word, with_final, without_final)}"


# 시간 단위 환산 — '1시간'과 '60분'이 같은 값임을 알아야 모순을 판별할 수 있다.
TIME_UNITS = {"초": 1 / 60, "분": 1.0, "시간": 60.0, "일": 1440.0}

# 단위 뒤에는 조사나 구두점만 올 수 있다 — '분석', '일과' 같은 낱말을 걸러내기 위함.
_AFTER_UNIT = r"(?=[\s,.)\]]|$|이|가|을|를|에|으|까|은|는|의|만|도|씩|와|과|짜|부터|→|~)"
_TIME_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(초|분|시간|일)" + _AFTER_UNIT)
_TRANSITION_RE = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(초|분|시간|일)\s*(?:에서|부터|→|~)\s*"
    r"(\d[\d,]*(?:\.\d+)?)\s*(초|분|시간|일)"
)


def _minutes(number: str, unit: str) -> float:
    return float(number.replace(",", "")) * TIME_UNITS[unit]


def time_values(text: str) -> list[tuple[str, float]]:
    """텍스트의 모든 시간 표현을 (원문, 분 단위 값)으로 돌려준다."""
    out = []
    for match in _TIME_RE.finditer(normalize_newlines(text)):
        out.append((match.group(0).strip(), _minutes(match.group(1), match.group(2))))
    return out


def time_transitions(text: str) -> list[tuple[str, float, float]]:
    """'A에서 B로' 형태의 변화 서술을 (원문, 시작값, 끝값)으로 돌려준다."""
    out = []
    for match in _TRANSITION_RE.finditer(normalize_newlines(text)):
        out.append((
            match.group(0).strip(),
            _minutes(match.group(1), match.group(2)),
            _minutes(match.group(3), match.group(4)),
        ))
    return out


def time_equivalents(token: str) -> set[str]:
    """'90분' → {'90분', '1.5시간'} 처럼 같은 값의 다른 표기를 만든다."""
    match = _TIME_RE.fullmatch(canonical_number(token))
    if not match:
        return set()
    minutes = _minutes(match.group(1), match.group(2))
    out = set()
    for unit, factor in TIME_UNITS.items():
        value = minutes / factor
        if value <= 0:
            continue
        text = f"{value:g}"
        out.add(canonical_number(text + unit))
    return out
