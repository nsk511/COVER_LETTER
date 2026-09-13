"""Anthropic API 호출 (선택 기능).

API 키가 없어도 이 도구는 동작한다. 키가 없으면 `jaso prompt` 로 만든
프롬프트를 Claude 앱에 붙여넣으면 된다. 키가 있으면 `jaso draft --write`
로 초안까지 자동 생성한다.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

DEFAULT_MODEL = os.environ.get("JASO_MODEL", "claude-opus-5")
MAX_TOKENS = 16000

_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMUnavailable(RuntimeError):
    """API를 쓸 수 없을 때 — 사용자에게 그대로 보여줄 안내 메시지를 담는다."""


@dataclass
class DraftResult:
    subtitle: str
    body: str
    todo: str = ""
    raw: str = ""


def available() -> bool:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    )


def _client():
    try:
        import anthropic
    except ImportError as exc:
        raise LLMUnavailable(
            "anthropic 패키지가 설치되어 있지 않습니다.\n"
            "  pip install anthropic\n"
            "설치 없이 쓰려면: jaso prompt 로 프롬프트를 만들어 Claude 앱에 붙여넣으세요."
        ) from exc
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise LLMUnavailable(
            "ANTHROPIC_API_KEY 환경변수가 없습니다.\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...\n"
            "키 없이 쓰려면: jaso prompt 로 프롬프트를 만들어 Claude 앱에 붙여넣으세요."
        )
    return anthropic.Anthropic()


def _call(client, system: str, user: str, model: str):
    """정책 거절 시 서버측 폴백을 켜서 호출한다(지원되지 않으면 일반 호출)."""
    try:
        return client.beta.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            betas=[_FALLBACK_BETA],
            fallbacks="default",
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except Exception:  # 베타 미지원 환경이면 표준 호출로 재시도
        return client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )


def _text_of(response) -> str:
    parts = []
    for block in response.content:
        if getattr(block, "type", "") == "text":
            parts.append(block.text)
    return "\n".join(parts).strip()


def _parse(text: str) -> DraftResult:
    """'소제목: / 본문: / 확인필요:' 형식을 파싱한다."""
    subtitle = ""
    body_lines: list[str] = []
    todo_lines: list[str] = []
    section = None

    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^소제목\s*[:：]", stripped):
            subtitle = re.sub(r"^소제목\s*[:：]\s*", "", stripped).strip(" []")
            section = None
            continue
        if re.match(r"^본문\s*[:：]", stripped):
            section = "body"
            rest = re.sub(r"^본문\s*[:：]\s*", "", stripped)
            if rest:
                body_lines.append(rest)
            continue
        if re.match(r"^확인\s*필요\s*[:：]", stripped):
            section = "todo"
            rest = re.sub(r"^확인\s*필요\s*[:：]\s*", "", stripped)
            if rest:
                todo_lines.append(rest)
            continue
        if section == "body":
            body_lines.append(line.rstrip())
        elif section == "todo":
            todo_lines.append(stripped)

    body = "\n".join(body_lines).strip()
    if not body and not subtitle:
        body = text.strip()
    todo = "\n".join(t for t in todo_lines if t and t != "없음").strip()
    return DraftResult(subtitle=subtitle, body=body, todo=todo, raw=text)


def generate(system: str, user: str, model: str = DEFAULT_MODEL) -> DraftResult:
    client = _client()
    response = _call(client, system, user, model)

    if getattr(response, "stop_reason", "") == "refusal":
        raise LLMUnavailable(
            "모델이 요청을 거절했습니다. 프롬프트에 민감한 내용이 있는지 확인하세요.\n"
            "  jaso prompt 로 프롬프트를 확인할 수 있습니다."
        )
    return _parse(_text_of(response))
