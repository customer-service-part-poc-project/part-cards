# CLAUDE.md

고객서비스파트 카드 사이트 빌더. 데이터는 `part-wiki/data/` 이고 여기에는 코드만 둔다. 설명은 [README.md](README.md).

- `scripts/cards_data.py` — 적재(`load_local`·`load_remote`)와 스키마 검증.
- `scripts/build_site.py` — HTML 렌더링만. 표준 라이브러리, CSS 인라인, JS·CDN 없음. 모든 카드 문자열은 `esc()` 를 거친다.
- `scripts/test_cards_data.py` — 검증 규칙과 공개 범위 테스트. **커밋해서 유지한다** (워크플로가 빌드 전에 돌린다).
  `python3 -m unittest discover -s scripts -p 'test_*.py'`
- **public 저장소·public 사이트다.** 위키 본문·대화 원문·조직 저장소 통계를 넣는 코드를 쓰지 않는다. 금지 패턴은 `cards_data.py` 의 `FORBIDDEN_*` · `forbidden_patterns()`.
- **코드에 실명을 두지 않는다.** 카드에 실리면 안 되는 이름은 `CARDS_FORBIDDEN_NAMES` 시크릿(쉼표 구분)에서 읽는다. 비어 있으면 이름 검사는 건너뛴다.
- **이모지 반응 집계는 싣지 않는다.** 데이터에 키가 남아 있어도 검증은 통과시키고 렌더에서 무시한다.
- 한 건이 어긋나면 그 파일만 건너뛴다. 0건이어도 빌드는 성공한다.
- 로컬 확인: `python3 scripts/build_site.py --local ../part-wiki --out _site`.
- 커밋 메시지는 gitmoji 로 시작한다 (✨ 기능, 🐛 버그, ♻️ 리팩터링, 📝 문서, 🔧 설정).
