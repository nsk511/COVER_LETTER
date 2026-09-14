# jaso — 자기소개서 & 면접 준비 도구

경력 노트(내가 실제로 한 일)를 한 번 정리해 두면, 지원하는 회사마다
**인재상 매칭 → 문항별 설계 → 초안 → 검증 → 면접 예상질문**까지 이어서 만들어 줍니다.

이 도구의 전제는 하나입니다. **경력 노트에 없는 내용은 자소서에 쓰지 않는다.**
지어낸 문장은 자소서를 통과시켜도 면접에서 무너지기 때문입니다.

**웹 버전(고정 URL)**: https://claude.ai/code/artifact/85ae0c8e-f35e-4390-8e40-0fa43989d001
설치 없이 브라우저에서 같은 흐름을 쓸 수 있고, 경력 노트가 저장됩니다.
소스는 `web/index.html` 이며, 같은 주소로 계속 갱신됩니다.

---

## 1. 설치

파이썬 3.11 이상, 외부 패키지는 `PyYAML` 하나만 필요합니다.

```bash
pip install pyyaml
# (선택) 초안 자동 생성까지 쓰려면
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
```

API 키가 없어도 됩니다. 키가 없으면 `jaso prompt` 가 **붙여넣기용 프롬프트**를
만들어 주므로, 그걸 Claude 앱에 넣으면 같은 결과를 얻습니다.

실행은 저장소 폴더에서:

```bash
python3 -m jaso --help
```

편하게 쓰려면 별칭을 만들어 두세요.

```bash
alias jaso='python3 -m jaso'
```

---

## 2. 5분 사용법

```bash
jaso init          # career.yaml, company.yaml, draft.yaml 생성
# career.yaml  ← 본인의 실제 경험을 채웁니다 (가장 중요)
# company.yaml ← 공고의 문항·글자수·인재상을 그대로 옮깁니다

jaso match         # 이 회사 인재상에 어떤 경험이 맞는지 점수로 확인
jaso plan          # 문항별 문단 구성·목표 글자수·쓸 경험·소제목 후보
jaso prompt --write   # 프롬프트 생성 (또는 jaso draft — API 키 필요)
# draft.yaml 에 초안을 붙여넣은 뒤
jaso lint          # 글자수·지어낸 수치·클리셰·치명적 약점 검증
jaso interview --write   # 면접 예상질문 + 준비표(Excel)
jaso export        # 위 산출물 전체를 out/ 폴더에 저장
```

---

## 3. 명령어

| 명령 | 하는 일 |
|---|---|
| `init` | 템플릿 3종 생성 (`--force` 로 덮어쓰기) |
| `match` | 회사 인재상을 역량축으로 해석하고 경험별 점수·커버리지 산출 |
| `plan` | 문항 유형별 문단 배분, 목표 글자수, 주 경험/대안, 소제목 후보 |
| `prompt` | 문항별 LLM 프롬프트 생성 (`-q q2` 로 한 문항만) |
| `draft` | API로 초안 생성해 `draft.yaml` 에 저장 (키 없으면 prompt로 대체) |
| `lint` | 초안 검증. `--strict` 면 오류 시 종료코드 1 |
| `interview` | 예상질문·꼬리질문·구술 스크립트 생성 |
| `export` | 모든 산출물을 `out/` 에 저장 (제출용 `자기소개서.md` 포함) |

공통 옵션: `--career`, `--company`, `--draft`, `--out`

---

## 4. 검증 규칙 (`jaso lint`)

| 코드 | 잡아내는 것 |
|---|---|
| `LEN` | 글자수 초과/미달. 공백포함·공백제외 둘 다 계산 |
| `NUM` | **경력 노트에 없는 수치** — 지어낸 숫자 방지 (오류). 시간 단위는 환산해 비교("90분" ≡ "1.5시간") |
| `CONTRA` | **같은 답변 안에서 어긋나는 수치** (오류). "90분이 걸렸다 … 1시간에서 20분으로 줄였다" 같은 자기모순 |
| `FACT` | 출처(`research.source` + `checked: true`) 없는 회사 관련 주장 (오류) |
| `BALANCE` | 지원동기 문항에서 회사 이야기가 절반을 넘는 경우 (오류) |
| `WEAK` | 직무 핵심역량과 직결되는 치명적 약점 표현 (오류) |
| `CLICHE` | "쿼리 최적화", "불필요한 로직 제거" 같은 뭉뚱그린 표현 |
| `OVERTIME` | "야근", "퇴근 후" 등 근무 외 시간 강조 |
| `SUB` | 소제목 없음, 또는 [방법]+[결과] 공식에서 벗어남 |
| `SENT` | 95자 넘는 긴 문장이 많은 경우 |
| `SPACING` | 흔한 띄어쓰기 오류("노력하고있습니다", "한만큼")와 이중 공백 |
| `REF` | 대외비·미검증 경험 사용, 잘못된 경험 id 참조 |

`NUM`·`CONTRA` 두 규칙이 이 도구의 핵심입니다. 초안의 모든 숫자를 경력 노트의
`metrics` 및 본문과 대조하고, 한 답변 안에서 앞뒤 수치가 어긋나는지도 봅니다.
수정을 여러 번 거친 자소서에서 가장 자주 남는 사고가 이 두 가지입니다.

### 문항 유형

`motivation`(지원동기) · `achievement`(성과) · `challenge`(도전) · `collaboration`(협업)
· `strength`(강점) · `strength_weakness`(강점·약점) · `growth_story`(성장과정)
· `social_issue`(사회이슈) · `growth`(성장·학습) · `free`

유형에 따라 문단 배분과 검증 방식이 달라집니다. 소제목 [방법]+[결과] 공식은
성취·강점 계열에만 적용하고, 성장과정·사회이슈 문항에는 강제하지 않습니다.

---

## 5. 파일 구조

```
web/index.html # 웹 버전 (아티팩트로 배포되는 단일 페이지)
career.yaml    # 경력 노트 — 한 번 만들어 회사마다 재사용
company.yaml   # 회사·직무·인재상·문항·글자수·리서치
draft.yaml     # 문항별 초안 (소제목 / 본문 / 근거 경험)
out/           # 산출물
```

`career.yaml` 의 경험 한 건은 STAR + 도메인 통찰 + 수치로 구성됩니다.

```yaml
experiences:
  - id: exp-rate-agg
    title: 요율산출 집계 단위 재설계
    situation: ...        # 어떤 상황이었나
    task: ...             # 내가 맡은 것
    action: ...           # 무엇을 했나
    result: ...           # 어떻게 됐나
    insight: ...          # 왜 그 방법이 가능했나 ← 면접에서 가장 많이 묻는 지점
    difficulty: ...       # 어려웠던 점
    metrics:
      - {name: 산출 시간, before: 90분, after: 20분, delta: 78% 단축}
    confidential: true    # 고객사명 등은 일반화해서 쓰라고 경고해 줍니다
```

`insight` 를 비워두면 `plan` 과 `interview` 가 "여기가 가장 많이 물어보는
지점인데 비어 있다"고 알려 줍니다. 자소서의 강도는 대부분 이 칸에서 갈립니다.

---

## 6. 회사 리서치 규칙

지원동기 문항은 회사 리서치 없이 쓰지 않습니다. `company.yaml` 에 이렇게 적습니다.

```yaml
research:
  - claim: 2026년 ○○ 안전 캠페인 3회차 시행
    source: https://...       # 실제 기사/공식 페이지
    date: 2026-08-20
    checked: true             # 직접 확인했을 때만 true
```

`checked: true` 인 항목만 프롬프트의 "인용 가능한 사실"에 들어가고,
그 외의 회사 관련 주장은 `lint` 가 `FACT` 오류로 잡습니다.
가능하면 **올해 자료**를 쓰고, 여러 후보가 있으면 본인 직무와 논리적으로
가장 자연스럽게 이어지는 것을 고르세요.

---

## 7. 테스트

```bash
python3 -m unittest discover -s tests
```

---

## 8. 한계

- 회사 리서치는 자동으로 수집하지 않습니다. 직접 확인해 `research` 에 넣으세요.
- 문장 분해·클리셰 탐지는 규칙 기반 휴리스틱이라 100%가 아닙니다. 경고는 참고용,
  오류(`ERROR`)만 반드시 고치면 됩니다.
- 최종 판단은 사람이 합니다. 초안은 반드시 본인이 읽고 사실 여부를 확인하세요.
