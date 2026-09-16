# CLAUDE.md

고객서비스파트 카드 사이트 빌더. 데이터는 `part-wiki/data/` 이고 여기에는 코드만 둔다. 설명은 [README.md](README.md).

- `scripts/cards_data.py` — 적재(`load_local`·`load_remote`)와 스키마 검증.
  - 카드는 네 종류다. `data/profiles/*.json` · `data/projects/*.json` 은 파일마다 한 장이고,
    `data/schedule.json`(파트 일정) · `data/changelog.json`(최근 변경)은 **파일 하나가 한 장**이다. 없으면 그 섹션만 빈다.
  - 업무일 2일 창(`business_window`·`events_in_window`)과 최근 7일(`entries_within`)은 순수 함수다.
    part-wiki `scripts/part_schedule.py` 와 **같은 규칙**이어야 한다 — 어긋나면 사이트와 텔레그램 요약이 달라진다.
- `scripts/build_site.py` — HTML 렌더링만. 표준 라이브러리, CSS 인라인, JS·CDN 없음. 모든 카드 문자열은 `esc()` 를 거친다.
  - 목록 섹션 순서는 **파트 일정 → 프로젝트 → 멤버 → 최근 변경** (변경은 줄 수가 많아 맨 아래, 2026-09-16). 프로젝트 앵커 `#projects` 는 유지한다.
  - 기준일은 `render_index(..., today=)` 로 넣는다 (기본 KST 오늘). 테스트가 날짜를 고정하는 자리다.
  - 색상 토큰은 `CSS` 의 `:root` 에 있다. 대표색 `--brand:#F37321` 은 한화 CI 의 Hanwha Orange (70% `#F89B6C`, 50% `#FBB584`). 흰 바탕에 오렌지가 CI 원칙이라 라이트 모드가 기준이고, 다크는 `--brand:#FF8F45` 로 한 단계 밝힌다. 근거는 part-wiki `wiki/notes/파트-브랜드-색상.md`.
  - 작은 글자에는 `--brand` 대신 `--brand-ink` 를 쓴다 — 흰 바탕에서 `#F37321` 은 대비 3:1 미만이라 본문 텍스트용이 아니다.
- `scripts/test_cards_data.py` — 검증 규칙과 공개 범위 테스트. **커밋해서 유지한다** (워크플로가 빌드 전에 돌린다).
  `python3 -m unittest discover -s scripts -p 'test_*.py'`
- **public 저장소·public 사이트다.** 위키 본문·대화 원문·조직 저장소 통계를 넣는 코드를 쓰지 않는다. 금지 패턴은 `cards_data.py` 의 `FORBIDDEN_*` · `forbidden_patterns()`.
- **코드에 실명을 두지 않는다.** 카드에 실리면 안 되는 이름은 `CARDS_FORBIDDEN_NAMES` 시크릿(쉼표 구분)에서 읽는다. 비어 있으면 이름 검사는 건너뛴다.
- **이모지 반응 집계는 싣지 않는다.** 데이터에 키가 남아 있어도 검증은 통과시키고 렌더에서 무시한다.
- 한 건이 어긋나면 그 파일만 건너뛴다. 0건이어도 빌드는 성공한다.
- 로컬 확인: `python3 scripts/build_site.py --local ../part-wiki --out _site`.
- 커밋 메시지는 gitmoji 로 시작한다 (✨ 기능, 🐛 버그, ♻️ 리팩터링, 📝 문서, 🔧 설정).
