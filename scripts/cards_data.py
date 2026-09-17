#!/usr/bin/env python3
"""part-wiki 의 data/ 카드 JSON 을 읽고 스키마를 검증한다 (build_site.py 가 쓴다).

데이터는 part-wiki(private) 의 네 종류다.

    data/profiles/*.json   사람 카드            docs/PROFILE_SCHEMA.md
    data/projects/*.json   과제 카드            docs/PROJECT_SCHEMA.md
    data/schedule.json     파트 일정 (한 파일)   docs/SCHEDULE_SCHEMA.md
    data/changelog.json    최근 변경 (한 파일)   docs/CHANGELOG_SCHEMA.md
    data/daily.json        업무 요약 (한 파일)   docs/DAILY_SCHEMA.md

위키 본문(projects/·members/·raw/)은 읽지 않는다 — 카드는 사람이 공개 범위를 골라 다시 쓴 요약이다.
공개 범위는 그 저장소의 docs/PRIVACY.md.

환경변수
  GH_TOKEN               part-wiki 를 읽을 PAT — ORG_READ_TOKEN (Contents: Read)
  ORG                    조직 로그인    (기본 customer-service-part-poc-project)
  WIKI_REPO              데이터 저장소  (기본 part-wiki)
  WIKI_REF               브랜치         (기본 main)
  CARDS_FORBIDDEN_NAMES  카드에 실으면 안 되는 사람 이름, 쉼표 구분 (비우면 이름 검사를 건너뛴다)

설계
- 표준 라이브러리만 사용한다.
- 카드 한 건이 스키마에 어긋나면 **그 파일만 건너뛰고** 사유를 남긴다. 한 사람의 실수로
  전체 카드가 사라지지 않게. 일정·변경은 파일이 하나라 그 섹션만 빠진다.
- `schedule.json`·`changelog.json`·`daily.json` 은 **없어도 정상**이다 (경고 없이 그 섹션만 비운다).
- 업무일 2일 창 계산(`business_window`·`events_in_window`)은 part-wiki 의 `scripts/part_schedule.py`
  와 같은 규칙이다. 한쪽을 고치면 다른 쪽도 고친다 — 어긋나면 사이트와 텔레그램 요약이 달라진다.
  사이트는 **오늘부터 업무일 3일**(`SITE_SCHEDULE_DAYS`, 오늘·내일·모레)을 그리고, 빌드 시각 기준 **지난 항목은 취소선**
  (`event_done`). 텔레그램 일일 요약은 같은 함수로 오늘 하루만 (2026-09-17).
- `daily.json` 은 날짜별 요약 묶음이다. 사이트는 **직전 업무일과 오늘** 두 날만 그린다 (`daily_days`) — 저녁에 봐도 아침에 봐도 덮이게.
- 이 저장소는 public 이다. 카드에 실으면 안 되는 이름은 코드가 아니라 `CARDS_FORBIDDEN_NAMES`
  시크릿에 둔다 — 소스에 실명을 적지 않는다.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta, timezone
from email.message import Message

API = "https://api.github.com"
KST = timezone(timedelta(hours=9), "KST")


class ApiError(Exception):
    """GitHub API 호출 실패."""


def warn(msg: str) -> None:
    print(f"::warning::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"경고: {msg}", file=sys.stderr)


class _SameHostRedirect(urllib.request.HTTPRedirectHandler):
    """urllib 은 호스트가 바뀌어도 Authorization 을 넘긴다 — api.github.com 밖으로는 따라가지 않는다."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        if urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(API).netloc:
            raise ApiError(f"외부 호스트로의 리다이렉트 거부: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_SameHostRedirect)


class GitHub:
    """Contents API 읽기 전용 최소 클라이언트."""

    def __init__(self, token: str) -> None:
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "part-cards-site-builder",
        }

    def get(self, path: str, params: dict[str, object] | None = None) -> tuple[object, Message]:
        # 파일명이 한글이면 ASCII 가 아니라 putrequest 에서 실패한다 — 경로 세그먼트를 퍼센트 인코딩한다.
        url = f"{API}{urllib.parse.quote(path, safe='/')}" + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, headers=self._headers)
        for attempt in range(1, 4):
            try:
                with _OPENER.open(req, timeout=30) as resp:
                    return json.load(resp), resp.headers
            except urllib.error.HTTPError as e:
                rate_limited = e.code == 429 or (e.code == 403 and e.headers.get("X-RateLimit-Remaining") == "0")
                if (e.code >= 500 or rate_limited) and attempt < 3:
                    time.sleep(2**attempt)
                    continue
                # 한 줄로 접는다 — ::error:: 주석은 첫 줄만 보여 준다.
                body = " ".join(e.read().decode("utf-8", errors="replace").split())[:300]
                raise ApiError(f"HTTP {e.code} {path}: {body}") from e
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < 3:
                    time.sleep(2**attempt)
                    continue
                raise ApiError(f"연결 실패 {path}: {e}") from e
        raise AssertionError("unreachable")


SCHEMA_VERSION = 1
DEFAULT_PART = "고객서비스파트"
BANNER = "MBTI·나이대는 추측이다. 말투 뱃지는 관측값이다. 업무 성향과 재미 코너를 섞어 읽지 않는다."

# ── 검증 규칙 (part-wiki/docs/PROFILE_SCHEMA.md · PROJECT_SCHEMA.md · PRIVACY.md) ────────────────
# 중첩 어디에 있어도 거부하는 키. 원문 인용과 성별 추정을 막는다.
FORBIDDEN_KEY_EXACT = ("raw_quote", "quotes", "gender", "성별")
FORBIDDEN_KEY_PREFIX = ("samples_",)

# JSON 전체를 문자열로 훑어 찾는 금지 패턴. 링크는 종류를 가리지 않고 막는다 — 카드에 링크를 싣지 않는다.
BASE_FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("URL", re.compile(r"https?://|www\.", re.I)),
    ("전화번호", re.compile(r"01[016-9][-\s]?\d{3,4}[-\s]?\d{4}")),
    ("이메일", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("주민등록번호 형태", re.compile(r"\d{6}[-\s]?[1-4]\d{6}")),
)


def forbidden_names() -> tuple[str, ...]:
    """카드에 실으면 안 되는 사람 이름. public 저장소라 소스가 아니라 환경변수에 둔다."""
    return tuple(n.strip() for n in os.environ.get("CARDS_FORBIDDEN_NAMES", "").split(",") if n.strip())


def forbidden_patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    """검사할 금지 패턴. 이름 목록이 비어 있으면 이름 검사는 건너뛴다 —
    빈 정규식은 모든 문자열에 걸리므로 반드시 분기한다. 시크릿을 갈아끼워도 다음 호출에 반영되도록
    상수가 아니라 함수로 둔다 (같은 목록이면 컴파일 결과를 재사용)."""
    names = forbidden_names()
    if not names:
        return BASE_FORBIDDEN_PATTERNS
    return BASE_FORBIDDEN_PATTERNS + (("금지 실명", _name_regex(names)),)


_name_cache: dict[tuple[str, ...], re.Pattern[str]] = {}


def _name_regex(names: tuple[str, ...]) -> re.Pattern[str]:
    rx = _name_cache.get(names)
    if rx is None:
        rx = re.compile("|".join(map(re.escape, names)))
        _name_cache[names] = rx
    return rx


UNSAFE_NAME = re.compile(r"[/\\:*?\"<>|\x00-\x1f]")
FUN_KEYS = (("mbti", "MBTI"), ("age_band", "나이대"), ("speech_badge", "말투 뱃지"))
RETIRED_FUN_KEYS = ("blood_type",)  # 근거가 0인 항목은 싣지 않는다

AXES = (
    ("delegation", "위임", "직접 처리", "위임·분담"),
    ("verification", "검증", "결과를 그대로 수용", "검증·팩트체크"),
    ("planning", "계획", "즉흥", "계획 우선"),
    ("thoroughness", "집요함", "요점만", "끝까지 파고듦"),
    ("exploration", "탐색", "단정형", "탐색·제안형"),
)

PROJECT_STATUSES = ("준비", "진행중", "보류", "완료")
PROJECT_STATUS_ORDER = {"진행중": 0, "준비": 1, "보류": 2, "완료": 3}
MILESTONE_STATES = ("done", "doing", "todo")

# 일정·변경 (docs/SCHEDULE_SCHEMA.md · docs/CHANGELOG_SCHEMA.md)
EVENT_KINDS = ("회의", "근태", "보고", "행사", "마감", "기타")
CHANGE_CARDS = ("profile", "project", "schedule", "site")
DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")  # 날짜 비교를 문자열로 하므로 형식이 어긋나면 받지 않는다
SCHEDULE_WINDOW_DAYS = 2  # 업무일 2일 (창 함수 기본값 — part_schedule.py 와 같다)
SITE_SCHEDULE_DAYS = 3  # 사이트 파트 일정 카드: 오늘·내일·모레 (2026-09-17)
CHANGELOG_KEEP_DAYS = 7
DAILY_MAX_ITEMS = 12  # 방 하나의 요약 줄 상한 — 카드는 한눈에 읽는 길이여야 한다
DAILY_MAX_ROOMS = 6
_WINDOW_SCAN_LIMIT = 400  # 휴일이 잘못 채워져도 무한 루프에 빠지지 않게


# ───────────────────────────────────────────────────────────────────────── 유틸


def text(v: object) -> str:
    return "" if v is None else str(v).strip()


def num(v: object, default: float = 0) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def str_list(v: object, limit: int | None = None) -> list[str]:
    items = [text(x) for x in v] if isinstance(v, list) else []
    items = [x for x in items if x]
    return items[:limit] if limit else items


def sub(d: dict[str, Any], key: str) -> dict[str, Any]:
    """d[key] 가 객체면 그것, 아니면 빈 dict. (get 을 두 번 부르면 타입이 좁혀지지 않는다)"""
    v = d.get(key)
    return v if isinstance(v, dict) else {}


# ───────────────────────────────────────────────────────────────────────── 검증


def scan_forbidden_keys(node: object, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}"
            ks = str(k)
            if ks in FORBIDDEN_KEY_EXACT or ks.startswith(FORBIDDEN_KEY_PREFIX):
                hits.append(p)
            hits.extend(scan_forbidden_keys(v, p))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            hits.extend(scan_forbidden_keys(v, f"{path}[{i}]"))
    return hits


def _version_errors(data: dict[str, Any]) -> list[str]:
    if data.get("schema_version") != SCHEMA_VERSION:
        return [f"schema_version: {SCHEMA_VERSION} 이어야 합니다 (현재 {data.get('schema_version')!r})"]
    return []


def _privacy_errors(data: dict[str, Any]) -> list[str]:
    """모든 카드가 함께 타는 공개 범위 검사 — 금지 키와 금지 패턴 (docs/PRIVACY.md)."""
    errors = [f"금지 키: {p} — 원문 인용·성별 추정은 넣지 않습니다 (docs/PRIVACY.md)" for p in scan_forbidden_keys(data)]
    blob = json.dumps(data, ensure_ascii=False)
    for label, rx in forbidden_patterns():
        m = rx.search(blob)
        if m:
            errors.append(f"금지 패턴({label}): {m.group(0)[:24]} — docs/PRIVACY.md")
    return errors


def _common_errors(data: dict[str, Any], stem: str) -> list[str]:
    """파일 하나가 카드 하나인 프로필·프로젝트용 — `name` 이 파일명과 같아야 한다."""
    errors = _version_errors(data)
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("name: 비어 있습니다")
    elif name.strip() != stem:
        errors.append(f"name: 파일명과 다릅니다 (name={name.strip()!r} · 파일={stem!r})")
    elif UNSAFE_NAME.search(name) or name.strip() in (".", ".."):
        errors.append(f"name: 파일 경로로 쓸 수 없는 문자가 있습니다 ({name.strip()!r})")
    return errors + _privacy_errors(data)


def validate_profile(data: object, stem: str) -> list[str]:
    """거부 사유 목록. 빈 리스트면 통과 (docs/PROFILE_SCHEMA.md)."""
    if not isinstance(data, dict):
        return [f"최상위가 객체가 아닙니다 (현재 {type(data).__name__})"]
    errors = _common_errors(data, stem)
    fun = data.get("fun")
    if fun is not None:
        if not isinstance(fun, dict):
            errors.append("fun: 객체이거나 null 이어야 합니다 (재미 코너를 빼려면 null)")
        else:
            for key, ko in FUN_KEYS:
                blk = fun.get(key)
                if not isinstance(blk, dict):
                    errors.append(f'fun.{key}: {{"value":…, "strength":…, "basis":…}} 객체가 필요합니다')
                elif not text(blk.get("strength")):
                    errors.append(f"fun.{key}.strength: 근거 강도 표기가 없습니다 ({ko})")
            for key in RETIRED_FUN_KEYS:
                if key in fun:
                    errors.append(f"fun.{key}: 근거가 없어 폐지된 항목입니다. JSON 에서 지우세요")
    return errors


def validate_project(data: object, stem: str) -> list[str]:
    """거부 사유 목록. 빈 리스트면 통과 (docs/PROJECT_SCHEMA.md)."""
    if not isinstance(data, dict):
        return [f"최상위가 객체가 아닙니다 (현재 {type(data).__name__})"]
    errors = _common_errors(data, stem)
    if not text(data.get("title")):
        errors.append("title: 비어 있습니다 (카드에 표시할 과제명)")
    status = text(data.get("status"))
    if status not in PROJECT_STATUSES:
        errors.append(f"status: {' | '.join(PROJECT_STATUSES)} 중 하나여야 합니다 (현재 {status!r})")
    ms = data.get("milestones", [])
    if ms is not None and not isinstance(ms, list):
        errors.append("milestones: 배열이어야 합니다")
    else:
        for i, m in enumerate(ms or []):
            if not isinstance(m, dict) or not text(m.get("label")):
                errors.append(f'milestones[{i}]: {{"label":…, "date":…, "state":…}} 객체가 필요합니다')
            elif text(m.get("state")) not in MILESTONE_STATES:
                errors.append(f"milestones[{i}].state: {' | '.join(MILESTONE_STATES)} 중 하나여야 합니다")
    for key in ("workstreams", "members", "recent"):
        v = data.get(key, [])
        if v is not None and not isinstance(v, list):
            errors.append(f"{key}: 배열이어야 합니다")
    for i, m in enumerate(data.get("members") or []):
        if not isinstance(m, dict) or not text(m.get("name")):
            errors.append(f'members[{i}]: {{"name":…, "role":…}} 객체가 필요합니다')
    return errors


def _date_errors(value: object, where: str, required: bool = True) -> list[str]:
    s = text(value)
    if not s:
        return [f"{where}: 비어 있습니다 (YYYY-MM-DD)"] if required else []
    if not DATE_RX.match(s):
        return [f"{where}: YYYY-MM-DD 형식이어야 합니다 (현재 {s!r})"]
    try:
        date.fromisoformat(s)
    except ValueError:
        return [f"{where}: 달력에 없는 날짜입니다 ({s!r})"]
    return []


def _valid_date(s: str) -> bool:
    """형식이 맞고 달력에 있는 날짜인지 (2026-09-31 은 형식은 맞지만 없다)."""
    return not _date_errors(s, "")


def _event_errors(e: object, where: str, recurring: bool) -> list[str]:
    """events[] 와 recurring[] 이 공유하는 검사 — kind 는 여섯 값, label 은 비어 있지 않음."""
    if not isinstance(e, dict):
        return [f"{where}: 객체가 아닙니다"]
    errors: list[str] = []
    kind = text(e.get("kind"))
    if kind not in EVENT_KINDS:
        errors.append(f"{where}.kind: {' | '.join(EVENT_KINDS)} 중 하나여야 합니다 (현재 {kind!r})")
    if not text(e.get("label")):
        errors.append(f"{where}.label: 비어 있습니다 (카드에 찍을 한 줄)")
    if not recurring:
        errors.extend(_date_errors(e.get("date"), f"{where}.date"))
        errors.extend(_date_errors(e.get("end"), f"{where}.end", required=False))
        start, end = text(e.get("date")), text(e.get("end"))
        if end and DATE_RX.match(start) and DATE_RX.match(end) and end < start:
            errors.append(f"{where}.end: date 이상이어야 합니다 ({start} → {end})")
    else:
        wd = e.get("weekdays")
        if not isinstance(wd, list) or not wd:
            errors.append(f"{where}.weekdays: 0=월 … 6=일 정수 배열이 필요합니다")
        else:
            bad = [d for d in wd if not isinstance(d, int) or isinstance(d, bool) or not 0 <= d <= 6]
            if bad:
                errors.append(f"{where}.weekdays: 0~6 정수만 들어갑니다 (현재 {bad!r})")
        # from·until 도 문자열로 비교하므로 형식이 어긋나면 전개 범위가 조용히 틀어진다
        for key in ("from", "until"):
            errors.extend(_date_errors(e.get(key), f"{where}.{key}", required=False))
    return errors


def validate_schedule(data: object) -> list[str]:
    """거부 사유 목록. 빈 리스트면 통과 (docs/SCHEDULE_SCHEMA.md '검증').

    파일이 하나라 어긋나면 일정 섹션만 빠지고 나머지 카드는 그대로 나온다.
    `name` 검사는 하지 않는다 — 사람 카드와 달리 파일명이 곧 카드 이름이 아니다.
    """
    if not isinstance(data, dict):
        return [f"최상위가 객체가 아닙니다 (현재 {type(data).__name__})"]
    errors = _version_errors(data)
    holidays = data.get("holidays")
    if holidays is not None and not isinstance(holidays, list):
        errors.append("holidays: YYYY-MM-DD 배열이어야 합니다")
    else:
        for i, h in enumerate(holidays or []):
            errors.extend(_date_errors(h, f"holidays[{i}]"))
    for key, recurring in (("events", False), ("recurring", True)):
        v = data.get(key)
        if v is None:
            continue  # 없으면 빈 배열로 본다
        if not isinstance(v, list):
            errors.append(f"{key}: 배열이어야 합니다")
            continue
        for i, e in enumerate(v):
            errors.extend(_event_errors(e, f"{key}[{i}]", recurring))
    return errors + _privacy_errors(data)


def validate_changelog(data: object) -> list[str]:
    """거부 사유 목록. 빈 리스트면 통과 (docs/CHANGELOG_SCHEMA.md '검증')."""
    if not isinstance(data, dict):
        return [f"최상위가 객체가 아닙니다 (현재 {type(data).__name__})"]
    errors = _version_errors(data)
    keep = data.get("keep_days")
    if keep is not None and (not isinstance(keep, int) or isinstance(keep, bool) or keep < 1):
        errors.append(f"keep_days: 1 이상의 정수여야 합니다 (현재 {keep!r})")
    entries = data.get("entries")
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        errors.append("entries: 배열이어야 합니다")
        entries = []
    for i, e in enumerate(entries):
        where = f"entries[{i}]"
        if not isinstance(e, dict):
            errors.append(f"{where}: 객체가 아닙니다")
            continue
        errors.extend(_date_errors(e.get("date"), f"{where}.date"))
        cardk = text(e.get("card"))
        if cardk not in CHANGE_CARDS:
            errors.append(f"{where}.card: {' | '.join(CHANGE_CARDS)} 중 하나여야 합니다 (현재 {cardk!r})")
        if not text(e.get("summary")):
            errors.append(f"{where}.summary: 비어 있습니다 (무엇이 바뀌었는지 한 줄)")
    return errors + _privacy_errors(data)


def _room_errors(r: object, where: str) -> list[str]:
    if not isinstance(r, dict):
        return [f"{where}: 객체가 아닙니다"]
    errors = []
    if not text(r.get("room")):
        errors.append(f"{where}.room: 비어 있습니다 (방 이름)")
    cnt = r.get("count", 0)
    if not isinstance(cnt, int) or isinstance(cnt, bool) or cnt < 0:
        errors.append(f"{where}.count: 0 이상의 정수여야 합니다 (현재 {cnt!r})")
    items = r.get("items")
    if items is None:
        items = []
    if not isinstance(items, list):
        return errors + [f"{where}.items: 배열이어야 합니다"]
    if len(items) > DAILY_MAX_ITEMS:
        errors.append(f"{where}.items: {DAILY_MAX_ITEMS}줄 이하여야 합니다 (현재 {len(items)})")
    for j, it in enumerate(items):
        if not isinstance(it, str) or not it.strip():
            errors.append(f"{where}.items[{j}]: 비어 있지 않은 문자열이어야 합니다")
    return errors


def validate_daily(data: object) -> list[str]:
    """거부 사유 목록. 빈 리스트면 통과 (docs/DAILY_SCHEMA.md '검증').

    날짜마다 방별 요약 줄 목록이다. 줄은 위키 본문 인용이 아니라 동기화 때 LLM 이 쓴 한 줄 요약이고,
    링크·전화번호 등 금지 패턴은 다른 카드와 같이 `_privacy_errors` 가 막는다.
    """
    if not isinstance(data, dict):
        return [f"최상위가 객체가 아닙니다 (현재 {type(data).__name__})"]
    errors = _version_errors(data)
    days = data.get("days")
    if days is None:
        days = []
    if not isinstance(days, list):
        errors.append("days: 배열이어야 합니다")
        days = []
    seen: set[str] = set()
    for i, d in enumerate(days):
        where = f"days[{i}]"
        if not isinstance(d, dict):
            errors.append(f"{where}: 객체가 아닙니다")
            continue
        errors.extend(_date_errors(d.get("date"), f"{where}.date"))
        key = text(d.get("date"))
        if key in seen:
            errors.append(f"{where}.date: 같은 날짜가 두 번 있습니다 ({key})")
        seen.add(key)
        rooms = d.get("rooms")
        if rooms is None:
            rooms = []
        if not isinstance(rooms, list):
            errors.append(f"{where}.rooms: 배열이어야 합니다")
            continue
        if len(rooms) > DAILY_MAX_ROOMS:
            errors.append(f"{where}.rooms: {DAILY_MAX_ROOMS}개 이하여야 합니다 (현재 {len(rooms)})")
        for j, r in enumerate(rooms):
            errors.extend(_room_errors(r, f"{where}.rooms[{j}]"))
    return errors + _privacy_errors(data)


# ─────────────────────────────────────────────────────── 업무일 창 (일정·변경 공통)
#
# part-wiki 의 scripts/part_schedule.py 와 **같은 규칙**이다. 사이트와 텔레그램 요약이
# 같은 날짜를 보게 하려고 순수 함수로 떼어 두었다 (docs/SCHEDULE_SCHEMA.md).


def is_business_day(d: date, holidays: set[str]) -> bool:
    """월~금이고 holidays(YYYY-MM-DD 문자열 집합)에 없는 날."""
    return d.weekday() < 5 and d.isoformat() not in holidays


def prev_business_day(d: date, holidays: object = ()) -> date:
    """`d` 직전 업무일. part-wiki `part_schedule.prev_business_day` 와 같다."""
    hol = {text(h) for h in (holidays if isinstance(holidays, (list, tuple, set)) else [])}
    d -= timedelta(days=1)
    n = 0
    while not is_business_day(d, hol) and n < _WINDOW_SCAN_LIMIT:
        d -= timedelta(days=1)
        n += 1
    return d


def daily_days(daily: object, today: date, holidays: object = ()) -> list[dict[str, Any]]:
    """업무 요약 카드에 그릴 날들 — **직전 업무일과 오늘**, 어제가 먼저·오늘이 아래 (시간순, 2026-09-17). 요약이 없는 날도 빈 블록으로 돌려준다."""
    d = daily if isinstance(daily, dict) else {}
    by_date = {text(x.get("date")): x for x in (d.get("days") or []) if isinstance(x, dict) and text(x.get("date"))}
    out = []
    for day in (prev_business_day(today, holidays), today):
        key = day.isoformat()
        src = by_date.get(key) or {}
        rooms = [r for r in (src.get("rooms") or []) if isinstance(r, dict) and text(r.get("room"))]
        out.append({"date": key, "rooms": rooms})
    return out


def event_done(e: dict[str, Any], now_date: date, now_hm: str = "") -> bool:
    """빌드 시각 기준 이미 지난 항목인가 — 사이트가 취소선을 긋는다 (2026-09-17).

    끝난 날(`end` 또는 `date`)이 오늘보다 앞이면 지났다. 오늘 것은 `time` 이 `HH:MM` 이고 `now_hm` 보다 앞일 때만.
    '오후'·'점심' 같은 말로 된 시각은 비교하지 않는다 (지났다고 단정할 근거가 없다).
    """
    last = text(e.get("end")) or text(e.get("date"))
    if not last or not _valid_date(last):
        return False
    if last < now_date.isoformat():
        return True
    if text(e.get("date")) == now_date.isoformat() and last == now_date.isoformat():
        t = text(e.get("time"))
        if now_hm and re.fullmatch(r"\d{2}:\d{2}", t) and re.fullmatch(r"\d{2}:\d{2}", now_hm):
            return t < now_hm
    return False


def business_window(today: date, holidays: object = (), days: int = SCHEDULE_WINDOW_DAYS) -> tuple[date, date]:
    """(창 시작, 창 끝). 기준일이 업무일이면 그날이 첫째 날, 아니면 다음 업무일.

    첫째 날부터 업무일을 `days` 개 세어 마지막 업무일이 창 끝이다.
    목 → (목, 금) · 금 → (금, 월) · 토 → (월, 화).
    """
    hs = {holidays} if isinstance(holidays, str) else {text(h) for h in (holidays or ())}
    start = today
    for _ in range(_WINDOW_SCAN_LIMIT):
        if is_business_day(start, hs):
            break
        start += timedelta(days=1)
    cur, counted = start, 1
    while counted < days:
        cur += timedelta(days=1)
        if (cur - start).days > _WINDOW_SCAN_LIMIT:
            break
        if is_business_day(cur, hs):
            counted += 1
    return start, cur


def _norm_event(e: dict[str, Any], day: str, end: str, recurring: bool) -> dict[str, Any]:
    return {
        "date": day,
        "end": end,
        "time": text(e.get("time")),
        "kind": text(e.get("kind")),
        "label": text(e.get("label")),
        "members": str_list(e.get("members")),
        "note": text(e.get("note")),
        "recurring": recurring,
        "ongoing": False,
    }


def events_in_window(schedule: object, today: date, days: int = SCHEDULE_WINDOW_DAYS) -> list[dict[str, Any]]:
    """창 안의 이벤트를 날짜순(같은 날은 time → label)으로 돌려준다.

    - 단발 이벤트: `date <= 창 끝` 이고 `(end 또는 date) >= 창 시작` 이면 들어온다.
      창 안의 주말·휴일에 걸린 이벤트도 보인다.
    - 반복 일정: 창 안의 **업무일**에만 전개한다 (주말·휴일에는 펴지 않는다).
      `weekdays` 에 요일이 있고 `from <= 날짜 <= until` 이어야 한다.
    """
    d = schedule if isinstance(schedule, dict) else {}
    holidays = {h for h in str_list(d.get("holidays"))}
    start, end = business_window(today, holidays, days)
    s_iso, e_iso = start.isoformat(), end.isoformat()

    out: list[dict[str, Any]] = []
    for e in d.get("events") or []:
        if not isinstance(e, dict):
            continue
        day = text(e.get("date"))
        if not _valid_date(day):
            continue
        tail = text(e.get("end"))
        if not _valid_date(tail) or tail == day:
            tail = ""  # part_schedule.py 와 같게 — 하루짜리는 end 를 비운다
        if day <= e_iso and (tail or day) >= s_iso:
            ev = _norm_event(e, day, tail, recurring=False)
            ev["ongoing"] = day < s_iso  # 창 시작 전에 시작해 아직 안 끝난 기간 일정 — "진행 중" 표식용
            out.append(ev)

    cur = start
    while cur <= end:
        if is_business_day(cur, holidays):
            iso = cur.isoformat()
            for r in d.get("recurring") or []:
                if not isinstance(r, dict):
                    continue
                wd = r.get("weekdays")
                if not isinstance(wd, list) or cur.weekday() not in wd:
                    continue
                frm, until = text(r.get("from")), text(r.get("until"))
                if (frm and iso < frm) or (until and iso > until):
                    continue
                out.append(_norm_event(r, iso, "", recurring=True))
        cur += timedelta(days=1)

    out.sort(key=lambda x: (x["date"], x["time"], x["label"]))
    return out


def entries_within(changelog: object, today: date, days: int | None = None) -> list[dict[str, Any]]:
    """오늘을 포함해 `days` 일 안의 변경 항목을 최신순으로. 같은 날은 파일에 적힌 순서를 지킨다.

    `days` 가 None 이면 `changelog.keep_days` (기본 7). 7 이면 today-6 까지 들어오고 today-7 은 빠진다.
    """
    d = changelog if isinstance(changelog, dict) else {}
    if days is None:
        keep = d.get("keep_days", CHANGELOG_KEEP_DAYS)
        days = keep if isinstance(keep, int) and not isinstance(keep, bool) and keep >= 1 else CHANGELOG_KEEP_DAYS
    floor = (today - timedelta(days=days - 1)).isoformat()
    ceil = today.isoformat()
    items: list[dict[str, Any]] = []
    for e in d.get("entries") or []:
        if not isinstance(e, dict):
            continue
        day = text(e.get("date"))
        if not DATE_RX.match(day) or not (floor <= day <= ceil):
            continue
        items.append(
            {
                "date": day,
                "card": text(e.get("card")),
                "target": text(e.get("target")),
                "summary": text(e.get("summary")),
            }
        )
    # reverse=True 로도 같은 키끼리의 원래 순서는 유지된다 (파이썬 정렬은 안정적이다)
    items.sort(key=lambda x: x["date"], reverse=True)
    return items


def project_progress(milestones: object) -> tuple[int, int, str]:
    """(완료 수, 전체 수, 다음 마일스톤). 진행 중인 것이 있으면 그것이 '다음'이다."""
    raw = milestones if isinstance(milestones, list) else []
    items: list[dict[str, Any]] = [m for m in raw if isinstance(m, dict) and text(m.get("label"))]
    done = sum(1 for m in items if text(m.get("state")) == "done")
    for want in ("doing", "todo"):
        for m in items:
            if text(m.get("state")) == want:
                return done, len(items), text(m.get("label"))
    return done, len(items), ""


def badge_short(badge: object) -> str:
    """목록 셀용 짧은 말투 뱃지 — `단정 3.5배` · `물결 안 씀`."""
    if not isinstance(badge, dict) or not text(badge.get("marker")):
        return ""
    marker = text(badge.get("marker"))
    if text(badge.get("kind")) == "안씀":
        return f"{marker} 안 씀"
    ratio = num(badge.get("ratio"))
    return f"{marker} {ratio:g}배" if ratio else marker


# ───────────────────────────────────────────────────────────────────────── 적재


# 디렉터리 하나에 카드 여러 장 / 파일 하나가 카드 한 장
CARD_DIRS = (("profile", "profiles"), ("project", "projects"))
CARD_FILES = (("schedule", "schedule.json"), ("changelog", "changelog.json"), ("daily", "daily.json"))


@dataclass
class Card:
    kind: str  # "profile" | "project" | "schedule" | "changelog" | "daily"
    file: str  # 표시용 경로 (profiles/김동준.json · schedule.json)
    data: dict[str, Any] | None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.data is not None and not self.errors


def _parse(kind: str, shown: str, raw: str) -> Card:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return Card(kind, shown, None, [f"JSON 파싱 실패 — {e.lineno}행 {e.colno}열: {e.msg}"])
    stem = Path(shown).stem
    if kind == "profile":
        errors = validate_profile(data, stem)
    elif kind == "project":
        errors = validate_project(data, stem)
    elif kind == "schedule":
        errors = validate_schedule(data)
    elif kind == "daily":
        errors = validate_daily(data)
    else:
        errors = validate_changelog(data)
    return Card(kind, shown, data if isinstance(data, dict) else None, errors)


def load_local(root: Path) -> list[Card]:
    cards: list[Card] = []
    for kind, sub_dir in CARD_DIRS:
        d = root / "data" / sub_dir
        if not d.is_dir():
            warn(f"디렉터리 없음: {d}")
            continue
        for jp in sorted(d.glob("*.json")):
            cards.append(_parse(kind, f"{sub_dir}/{jp.name}", jp.read_text(encoding="utf-8")))
    for kind, fname in CARD_FILES:
        fp = root / "data" / fname
        if fp.is_file():  # 없으면 그 섹션만 비운다 — 경고하지 않는다
            cards.append(_parse(kind, fname, fp.read_text(encoding="utf-8")))
    return cards


def _ensure_repo_visible(gh: GitHub, org: str, repo: str) -> None:
    """저장소 메타데이터가 404 면 토큰이 저장소를 못 보는 것이다 (없거나 만료됐거나 접근 권한이 빠짐)."""
    try:
        gh.get(f"/repos/{org}/{repo}")
    except ApiError as e:
        if "HTTP 404" in str(e):
            raise ApiError(
                f"{org}/{repo} 를 읽을 수 없다 (HTTP 404). 토큰(ORG_READ_TOKEN)이 없거나 만료됐거나 "
                f"이 저장소 Contents: Read 권한이 빠져 있다. 데이터 없음이 아니라 접근 실패다."
            ) from e
        raise


def load_remote(gh: GitHub, org: str, repo: str, ref: str) -> list[Card]:
    """Contents API 로 data/profiles · data/projects 를 받는다.

    디렉터리가 없으면(404) 비어 있는 것으로 본다. 다만 GitHub 은 토큰이 못 보는 private 저장소에도
    404 를 주므로, 저장소 자체가 안 보이면 "데이터 없음"이 아니라 오류로 올린다 — 그래야 빈 사이트가
    정상 배포로 덮어쓰지 않고 워크플로가 실패해 토큰 문제를 알린다.
    """
    cards: list[Card] = []
    for kind, sub_dir in CARD_DIRS:
        try:
            listing, _ = gh.get(f"/repos/{org}/{repo}/contents/data/{sub_dir}", {"ref": ref})
        except ApiError as e:
            if "HTTP 404" in str(e):
                _ensure_repo_visible(gh, org, repo)
                warn(f"{repo}/data/{sub_dir} 없음 — 건너뜀")
                continue
            raise
        if not isinstance(listing, list):
            raise ApiError(f"data/{sub_dir} 응답이 목록이 아님: {str(listing)[:200]}")
        for entry in sorted(listing, key=lambda e: str(e.get("name"))):
            name = str(entry.get("name", ""))
            if entry.get("type") != "file" or not name.endswith(".json"):
                continue
            body, _ = gh.get(f"/repos/{org}/{repo}/contents/{entry['path']}", {"ref": ref})
            if not isinstance(body, dict) or body.get("encoding") != "base64":
                cards.append(Card(kind, f"{sub_dir}/{name}", None, ["파일 본문을 받지 못했습니다 (1MB 초과?)"]))
                continue
            raw = base64.b64decode(str(body.get("content", ""))).decode("utf-8", errors="replace")
            cards.append(_parse(kind, f"{sub_dir}/{name}", raw))
    for kind, fname in CARD_FILES:
        try:
            body, _ = gh.get(f"/repos/{org}/{repo}/contents/data/{fname}", {"ref": ref})
        except ApiError as e:
            if "HTTP 404" in str(e):
                continue  # 아직 안 만든 파일이다 — 그 섹션만 비운다
            raise
        if not isinstance(body, dict) or body.get("encoding") != "base64":
            cards.append(Card(kind, fname, None, ["파일 본문을 받지 못했습니다 (1MB 초과?)"]))
            continue
        raw = base64.b64decode(str(body.get("content", ""))).decode("utf-8", errors="replace")
        cards.append(_parse(kind, fname, raw))
    return cards
