# part-cards — 고객서비스파트 멤버 · 프로젝트 카드 사이트

**https://customer-service-part-poc-project.github.io/part-cards/**

[`part-wiki`](https://github.com/customer-service-part-poc-project/part-wiki)(private) 의 `data/` 카드 JSON 을 읽어
정적 HTML 로 그리고 GitHub Pages 로 배포한다. 이 저장소에는 **코드만** 있고 데이터는 없다 — 카드 내용은 위키 저장소에서 고친다.

> ⚠️ 이 저장소와 사이트는 **public** 이다. 조직 private 저장소의 Pages 는 유료 플랜에서만 되기 때문에 사이트만 따로 뗐다.
> 그래서 위키 본문·대화 원문·조직 저장소 통계는 여기에 절대 싣지 않는다. 검색 엔진 색인은 `noindex` 로 막았지만 링크를 아는 사람은 누구나 본다.

## 어떻게 돌아가나

```
part-wiki/data/profiles/*.json  사람 카드   ─┐
part-wiki/data/projects/*.json  과제 카드   ─┤
part-wiki/data/daily.json       업무 요약   ─┼→ cards_data.py (검증) → build_site.py → _site/ → GitHub Pages
part-wiki/data/schedule.json    파트 일정   ─┤
part-wiki/data/changelog.json   최근 변경   ─┘
```

목록 페이지의 섹션 순서는 **업무 요약 → 파트 일정 → 프로젝트 → 멤버 → 최근 변경** 이다. 어제·오늘 한 일이 맨 위, 곧 있을 일이 그 다음, 변경 이력은 줄 수가 많아 맨 아래 (2026-09-17).
업무 요약은 `daily.json` 에서 **직전 업무일과 오늘** 두 날만 그린다 — 저녁에 봐도 아침에 봐도 덮이게. 요약이 없는 날은 "아직 없다"로 둔다.
일정은 **오늘부터 업무일 3일**(오늘·내일·모레, 주말·휴일 제외)이고 **빌드 시각 기준 지난 항목은 취소선**을 긋는다. 변경은 **7일** 치만 그린다.
`daily.json` · `schedule.json` · `changelog.json` 은 각각 **파일 하나**이고, 없으면 그 섹션만 빈 상태로 나온다.

`.github/workflows/pages.yml` 은 part-wiki 가 보내는 `wiki-data-updated` 신호를 받으면 돈다 — 카드 데이터가 바뀐 순간에만 다시 그린다.
그 밖에 매일 09:37 KST 안전망, 수동 실행(Actions → Run workflow), `scripts/` 변경 push 때도 돈다. 빌드 전에 `scripts/test_*.py` 를 먼저 돌린다.

## 처음 설정 (한 번만)

1. **Secret** — Settings → Secrets and variables → Actions → Secrets 에 `ORG_READ_TOKEN`
   (fine-grained PAT, Resource owner = 조직, 저장소 `part-wiki`, **Contents: Read**).
2. **Pages** — Settings → Pages → Build and deployment → Source = **GitHub Actions**.
3. (선택) **`CARDS_FORBIDDEN_NAMES`** 시크릿 — 카드에 실리면 안 되는 이름을 쉼표로 구분해 넣는다. 이 저장소는 public 이라 코드에 이름을 두지 않는다. 비워 두면 이름 검사만 건너뛴다.
4. **part-wiki 의 `CARDS_DISPATCH_TOKEN`** — fine-grained PAT, Resource owner = 조직, 저장소 `part-cards`,
   **Contents: Read and write**. 데이터 변경을 즉시 반영하는 주 경로다. 없거나 만료되면 하루 1회 안전망으로만 갱신된다.
   만료되면 part-wiki 의 `notify-cards.yml` 이 실패해 빨간불로 알려 준다.

## 무엇이 나가나

- 무엇을 싣고 뺄지는 part-wiki 의 `docs/PRIVACY.md` 와 스키마 다섯 장(`PROFILE_SCHEMA.md` · `PROJECT_SCHEMA.md` ·
  `SCHEDULE_SCHEMA.md` · `CHANGELOG_SCHEMA.md` · `DAILY_SCHEMA.md`)이 정한다
- 링크·전화번호·이메일·주민번호 형태·원문 인용 키가 있으면 **그 파일만** 건너뛰고 index 하단에 사유를 남긴다
- **업무 요약** — 날짜별·파트 방별로 동기화 때 LLM 이 쓴 한 줄 요약 몇 개와 메시지 수. **원문 인용·링크·고객 정보 없음** (`DAILY_SCHEMA.md`)
- **파트 일정** — 날짜·종류·한 줄 라벨·파트원 이름만. 근태는 구분만 적고 **사유는 싣지 않는다**. 회식은 장소·메뉴 없음
- **최근 변경** — 어느 카드가 언제 무엇 때문에 바뀌었는지 한 줄. 위키 본문을 옮기지 않는다
- **이모지 반응 집계는 싣지 않는다** — 데이터에 남아 있어도 카드에 그리지 않는다
- MBTI·나이대는 추측이라 근거 강도가 붙는다. 본인이 원하면 위키에서 자기 JSON 의 `fun` 을 `null` 로 둔다
- 카드가 0건이어도 사이트는 만들어진다

## 로컬에서 확인

```bash
python3 -m unittest discover -s scripts -p 'test_*.py'          # 검증 규칙 테스트
python3 scripts/build_site.py --local ../part-wiki --out _site   # 옆에 위키 클론이 있을 때, 토큰 불필요
open _site/index.html
```

표준 라이브러리만 쓴다 (Python 3.12+, CI 는 3.14 로 검증). `_site/` 는 커밋하지 않는다.
