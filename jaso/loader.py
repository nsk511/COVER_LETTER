"""YAML 입출력과 내장 사전 로딩."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

from .models import CareerNote, CompanyProfile, Draft

DATA_DIR = Path(__file__).resolve().parent / "data"


class LoadError(Exception):
    """사용자에게 그대로 보여줄 수 있는 로딩 오류."""


def read_yaml(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise LoadError(f"파일을 찾을 수 없습니다: {path}")
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise LoadError(f"YAML 형식 오류 ({path}): {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise LoadError(f"최상위가 키-값 구조여야 합니다: {path}")
    return data


def write_yaml(path: str | Path, data: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False, width=100)
    return path


def write_text(path: str | Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def load_career(path: str | Path) -> CareerNote:
    note = CareerNote.from_dict(read_yaml(path))
    if not note.experiences:
        raise LoadError(
            f"경력 노트에 experiences 항목이 없습니다: {path}\n"
            "  jaso init 으로 만든 템플릿을 채운 뒤 다시 실행하세요."
        )
    return note


def load_company(path: str | Path) -> CompanyProfile:
    profile = CompanyProfile.from_dict(read_yaml(path))
    if not profile.name:
        raise LoadError(f"회사 파일에 company.name 이 없습니다: {path}")
    if not profile.questions:
        raise LoadError(f"회사 파일에 questions(자소서 문항)가 없습니다: {path}")
    seen: set[str] = set()
    for question in profile.questions:
        if question.id in seen:
            raise LoadError(f"문항 id가 중복됩니다: {question.id}")
        seen.add(question.id)
    return profile


def load_draft(path: str | Path) -> Draft:
    return Draft.from_dict(read_yaml(path))


@functools.lru_cache(maxsize=None)
def _load_data(name: str) -> dict[str, Any]:
    return read_yaml(DATA_DIR / name)


def talent_axes() -> dict[str, dict[str, Any]]:
    return _load_data("talent_axes.yaml").get("axes", {})


def lint_rules() -> dict[str, Any]:
    return _load_data("lint_rules.yaml")


def domain_terms() -> list[str]:
    data = _load_data("domain_terms.yaml")
    terms: list[str] = []
    for values in data.values():
        for term in values or []:
            if term not in terms:
                terms.append(str(term))
    return terms
