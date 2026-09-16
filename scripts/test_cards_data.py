#!/usr/bin/env python3
"""cards_data.py 의 검증 규칙과 build_site.py 의 공개 범위를 테스트한다.

근거: part-wiki 의 docs/PROFILE_SCHEMA.md · docs/PROJECT_SCHEMA.md · docs/SCHEDULE_SCHEMA.md ·
docs/CHANGELOG_SCHEMA.md · docs/PRIVACY.md. 표준 라이브러리만 쓴다.

    python3 -m unittest discover -s scripts -p 'test_*.py'
"""
from __future__ import annotations

import base64
import copy
import datetime
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import build_site  # noqa: E402
import cards_data  # noqa: E402


def make_profile() -> dict:
    """docs/PROFILE_SCHEMA.md 기준의 정상 프로필."""
    return {
        "schema_version": 1,
        "name": "김동준",
        "part": "고객서비스파트",
        "role": "BE",
        "generated": "2026-09-15",
        "sources": ["telegram:고객서비스파트"],
        "signals": {
            "utterances": 32,
            "total_chars": 4461,
            "avg_chars": 139,
            "chat_chars": 2174,
            "avg_chat_chars": 67,
            "active_hours": "07~18",
            "markers": {"존댓말요": 33, "습니다체": 14, "단정": 3},
            "endings_top": ["습니다", "입니다", "있어요"],
            "artifacts": 12,
            "confidence": "높음",
            "badge": {"marker": "단정", "ratio": 3.5, "count": 3, "kind": "많이"},
        },
        "profile": {
            "axes": {
                "delegation": 2,
                "verification": 5,
                "planning": 4,
                "thoroughness": 5,
                "exploration": 3,
            },
            "work_style": "관측된 행동 근거로만 쓴 2~3줄짜리 설명이다.",
            "strengths": ["근거 있는 강점 1", "근거 있는 강점 2"],
        },
        "fun": {
            "mbti": {"value": "INTJ", "strength": "약함", "basis": "축별 근거 한 줄"},
            "age_band": {"value": "30대 중후반", "strength": "약함", "basis": "ㅋ 9건 · 존댓말 33건"},
            "speech_badge": {
                "value": "해야 한다고 말하는 사람",
                "strength": "관측",
                "basis": "단정 표현을 파트 평균의 3.5배로 쓴다 · 관측 32건",
            },
            "nickname": "먼저 정리해 오는 사람",
            "how_to_talk": {
                "good": ["확인하고 싶은 범위를 적어 보낸다"],
                "avoid": ["촉박한 마감과 함께 던지는 것"],
                "best_time": "07~09시",
                "example": "확인 부탁드립니다.",
            },
        },
    }


def make_project() -> dict:
    """docs/PROJECT_SCHEMA.md 기준의 정상 프로젝트."""
    return {
        "schema_version": 1,
        "name": "평생보장소득",
        "title": "평생 보장소득 은퇴설계 플랫폼",
        "part": "고객서비스파트",
        "status": "진행중",
        "phase": "사업계획 보고",
        "target": "2027-07 출시 1차안",
        "generated": "2026-09-15",
        "summary": "한 줄 정의",
        "badges": ["주력 과제"],
        "milestones": [
            {"label": "1차 보고", "date": "2026-08-20", "state": "done"},
            {"label": "부회장 보고", "date": "2026-09 중", "state": "doing"},
            {"label": "출시 1차안", "date": "2027-07", "state": "todo"},
        ],
        "workstreams": [{"area": "보고", "state": "진행중", "note": "2회 완료"}],
        "members": [{"name": "한민우", "role": "총괄"}],
        "next": ["부회장 보고"],
        "recent": [{"date": "2026-09-15", "note": "스크럼"}],
    }


# 2026-09-17 은 목요일이다. 업무일 창 테스트는 이 주를 기준으로 쓴다.
THU = datetime.date(2026, 9, 17)
FRI = datetime.date(2026, 9, 18)
SAT = datetime.date(2026, 9, 19)
SUN = datetime.date(2026, 9, 20)
MON = datetime.date(2026, 9, 21)
TUE = datetime.date(2026, 9, 22)


def make_schedule() -> dict:
    """docs/SCHEDULE_SCHEMA.md 기준의 정상 일정."""
    return {
        "schema_version": 1,
        "part": "고객서비스파트",
        "generated": "2026-09-16",
        "holidays": [],
        "events": [
            {"date": "2026-09-17", "time": "10:30", "kind": "회의", "label": "스크럼 의제", "members": ["김동준"], "note": ""},
            {"date": "2026-09-17", "end": "2026-09-18", "time": "", "kind": "보고", "label": "본부장 보고", "members": [], "note": "사업계획"},
        ],
        "recurring": [
            {"weekdays": [0, 1, 2, 3], "time": "10:30", "kind": "회의", "label": "스크럼", "members": [], "until": "2026-10-31", "note": ""},
        ],
    }


def make_changelog() -> dict:
    """docs/CHANGELOG_SCHEMA.md 기준의 정상 변경 목록."""
    return {
        "schema_version": 1,
        "part": "고객서비스파트",
        "keep_days": 7,
        "entries": [
            {"date": "2026-09-17", "card": "project", "target": "평생보장소득", "summary": "마일스톤 갱신"},
            {"date": "2026-09-17", "card": "profile", "target": "김동준", "summary": "말투 신호 갱신"},
            {"date": "2026-09-16", "card": "site", "target": "", "summary": "일정 카드 신설"},
        ],
    }


class ValidateProfileTests(unittest.TestCase):
    """docs/PROFILE_SCHEMA.md · docs/PRIVACY.md 의 검증 규칙."""

    def _errors(self, data, stem="김동준"):
        return cards_data.validate_profile(data, stem)

    def test_정상_프로필은_통과(self):
        self.assertEqual(self._errors(make_profile()), [])

    def test_schema_version이_다르면_거부(self):
        p = make_profile()
        p["schema_version"] = 2
        self.assertTrue(any("schema_version" in e for e in self._errors(p)))

    def test_파일명과_name이_다르면_거부(self):
        self.assertTrue(any("name" in e for e in self._errors(make_profile(), stem="한민우")))

    def test_금지_키_gender_거부(self):
        p = make_profile()
        p["gender"] = "남"
        self.assertTrue(any("금지 키" in e for e in self._errors(p)))

    def test_중첩된_금지_키도_거부(self):
        p = make_profile()
        p["profile"]["samples_원문"] = ["실제로 이렇게 말했다"]
        self.assertTrue(any("금지 키" in e for e in self._errors(p)))

    def test_mbti_근거강도가_없으면_거부(self):
        p = make_profile()
        del p["fun"]["mbti"]["strength"]
        self.assertTrue(any("fun.mbti.strength" in e for e in self._errors(p)))

    def test_폐지된_fun_키_거부(self):
        """혈액형처럼 근거가 0이라 폐지한 항목이 되살아나면 빌드가 막는다."""
        p = make_profile()
        p["fun"]["blood_type"] = {"value": "A형", "strength": "없음(무작위)", "basis": "데이터 신호 0"}
        self.assertTrue(any("blood_type" in e for e in self._errors(p)))

    def test_링크는_종류를_가리지_않고_거부(self):
        for url in (
            "https://www.notion.com/abc 문서를 참고해 처리한다.",
            "http://intra.example 로 들어가면 된다.",
            "www.example.co.kr 에 올려 두었다.",
        ):
            with self.subTest(url=url):
                p = make_profile()
                p["profile"]["work_style"] = url
                self.assertTrue(any("금지 패턴" in e for e in self._errors(p)))

    def test_전화번호_거부(self):
        p = make_profile()
        p["profile"]["work_style"] = "급할 때는 010-1234-5678 로 연락하면 된다."
        self.assertTrue(any("금지 패턴" in e for e in self._errors(p)))

    def test_이메일_거부(self):
        p = make_profile()
        p["profile"]["work_style"] = "문의는 someone@example.com 으로."
        self.assertTrue(any("금지 패턴" in e for e in self._errors(p)))

    def test_fun이_null이면_통과(self):
        p = make_profile()
        p["fun"] = None  # 본인이 재미 코너를 뺀 경우
        self.assertEqual(self._errors(p), [])

    def test_reactions_top이_있어도_검증은_통과(self):
        """수집기가 남긴 키다. 검증에서 막지 않고 렌더에서 무시한다."""
        p = make_profile()
        p["signals"]["reactions_top"] = [["👍", 14], ["❤", 4]]
        self.assertEqual(self._errors(p), [])


class ForbiddenNameTests(unittest.TestCase):
    """카드에 실으면 안 되는 이름은 소스가 아니라 CARDS_FORBIDDEN_NAMES 시크릿에 둔다."""

    def setUp(self):
        self._saved = os.environ.get("CARDS_FORBIDDEN_NAMES")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("CARDS_FORBIDDEN_NAMES", None)
        else:
            os.environ["CARDS_FORBIDDEN_NAMES"] = self._saved

    def test_등록된_이름이_있으면_거부(self):
        os.environ["CARDS_FORBIDDEN_NAMES"] = "홍길동, 임꺽정"
        p = make_profile()
        p["profile"]["work_style"] = "임꺽정 상무 보고 후 처리하는 편이다."
        self.assertTrue(any("금지 패턴" in e for e in cards_data.validate_profile(p, "김동준")))

    def test_프로젝트도_같은_검사를_탄다(self):
        os.environ["CARDS_FORBIDDEN_NAMES"] = "홍길동"
        pr = make_project()
        pr["recent"][0]["note"] = "홍길동 부사장 보고 완료"
        self.assertTrue(any("금지 패턴" in e for e in cards_data.validate_project(pr, "평생보장소득")))

    def test_목록이_비면_이름_검사를_건너뛴다(self):
        """빈 정규식은 모든 문자열에 걸린다 — 비었을 때 정상 카드가 통과하는지 확인한다."""
        os.environ["CARDS_FORBIDDEN_NAMES"] = ""
        self.assertEqual(cards_data.validate_profile(make_profile(), "김동준"), [])
        self.assertEqual(len(cards_data.forbidden_patterns()), len(cards_data.BASE_FORBIDDEN_PATTERNS))

    def test_공백만_있는_항목은_무시한다(self):
        os.environ["CARDS_FORBIDDEN_NAMES"] = " , ,  "
        self.assertEqual(cards_data.forbidden_names(), ())
        self.assertEqual(cards_data.validate_profile(make_profile(), "김동준"), [])


class ValidateProjectTests(unittest.TestCase):
    """프로젝트 JSON 도 프로필과 같은 공개 규칙을 탄다 (docs/PROJECT_SCHEMA.md)."""

    def _errors(self, data, stem="평생보장소득"):
        return cards_data.validate_project(data, stem)

    def test_정상_프로젝트는_통과(self):
        self.assertEqual(self._errors(make_project()), [])

    def test_파일명과_name이_다르면_거부(self):
        self.assertTrue(self._errors(make_project(), stem="변액"))

    def test_status는_정해진_값만(self):
        p = make_project()
        p["status"] = "하는중"
        self.assertTrue(any("status" in e for e in self._errors(p)))

    def test_마일스톤_state는_정해진_값만(self):
        p = make_project()
        p["milestones"][0]["state"] = "finished"
        self.assertTrue(any("milestones[0].state" in e for e in self._errors(p)))

    def test_title이_없으면_거부(self):
        p = make_project()
        p["title"] = ""
        self.assertTrue(any("title" in e for e in self._errors(p)))

    def test_링크_거부(self):
        p = make_project()
        p["summary"] = "자세한 내용은 https://www.notion.com/abc 참고"
        self.assertTrue(any("금지 패턴" in e for e in self._errors(p)))

    def test_금지_키_거부(self):
        p = make_project()
        p["workstreams"][0]["raw_quote"] = "원문 인용"
        self.assertTrue(any("금지 키" in e for e in self._errors(p)))

    def test_마일스톤과_담당이_비어도_통과(self):
        p = make_project()
        p["milestones"] = []
        p["members"] = []
        self.assertEqual(self._errors(p), [])


class ScanForbiddenKeyTests(unittest.TestCase):
    """금지 키는 중첩 어디에 있어도 경로째로 잡힌다."""

    def test_배열_안의_객체까지_훑는다(self):
        hits = cards_data.scan_forbidden_keys({"a": [{"quotes": ["원문"]}]})
        self.assertEqual(hits, ["$.a[0].quotes"])

    def test_접두사_규칙(self):
        self.assertEqual(cards_data.scan_forbidden_keys({"samples_원문": 1}), ["$.samples_원문"])

    def test_정상_데이터는_비어_있다(self):
        self.assertEqual(cards_data.scan_forbidden_keys(make_profile()), [])


class BadgeShortTests(unittest.TestCase):
    """목록 카드에 들어가는 말투 뱃지 칩. 별명과 겹치지 않게 짧아야 한다."""

    def test_배수_뱃지(self):
        self.assertEqual(cards_data.badge_short({"marker": "단정", "ratio": 3.5, "kind": "많이"}), "단정 3.5배")

    def test_안쓰는_것도_뱃지다(self):
        self.assertEqual(cards_data.badge_short({"marker": "물결", "ratio": 0.0, "kind": "안씀"}), "물결 안 씀")

    def test_값이_없으면_빈_문자열(self):
        for bad in (None, {}, {"ratio": 3.5}, "단정", []):
            self.assertEqual(cards_data.badge_short(bad), "")

    def test_칩이_짧다(self):
        """길면 카드에서 별명과 뒤엉킨다."""
        self.assertLessEqual(len(cards_data.badge_short({"marker": "위임분담", "ratio": 6.3, "kind": "많이"})), 12)


class ProjectProgressTests(unittest.TestCase):
    """진행률은 마일스톤 완료 수로만 계산한다. 사람이 % 를 적는 칸은 없다."""

    def test_완료_수와_전체_수(self):
        done, total, _ = cards_data.project_progress(make_project()["milestones"])
        self.assertEqual((done, total), (1, 3))

    def test_다음은_진행중이_우선(self):
        self.assertEqual(cards_data.project_progress(make_project()["milestones"])[2], "부회장 보고")

    def test_진행중이_없으면_첫_예정(self):
        ms = [{"label": "a", "state": "done"}, {"label": "b", "state": "todo"}]
        self.assertEqual(cards_data.project_progress(ms)[2], "b")

    def test_비어_있으면_0(self):
        self.assertEqual(cards_data.project_progress([]), (0, 0, ""))
        self.assertEqual(cards_data.project_progress(None), (0, 0, ""))


class ReactionsNotRenderedTests(unittest.TestCase):
    """이 사이트는 이모지 반응 집계를 싣지 않는다 — 데이터에 남아 있어도 HTML 에 나오면 안 된다."""

    def setUp(self):
        self.data = make_profile()
        self.data["signals"]["reactions_top"] = [["👍", 14], ["❤", 4], ["🎄", 2]]

    def test_목록_카드에도_상세에도_나오지_않는다(self):
        listing = build_site.member_card(copy.deepcopy(self.data), "m/김동준.html")
        detail = build_site.render_person(copy.deepcopy(self.data), "2026-09-16 10:00 KST")
        for html_out, where in ((listing, "목록 카드"), (detail, "상세 페이지")):
            with self.subTest(where=where):
                self.assertNotIn("👍", html_out)
                self.assertNotIn("❤", html_out)
                self.assertNotIn("반응", html_out)
                self.assertNotIn("mchip react", html_out)

    def test_말투_뱃지는_그대로_나온다(self):
        """반응만 빼고 관측값 렌더는 살아 있어야 한다."""
        self.assertIn("단정 3.5배", build_site.member_card(self.data, "m/김동준.html"))


class ValidateScheduleTests(unittest.TestCase):
    """docs/SCHEDULE_SCHEMA.md '검증'. 파일이 하나라 어긋나면 일정 섹션만 빠진다."""

    def _errors(self, data):
        return cards_data.validate_schedule(data)

    def test_정상_일정은_통과(self):
        self.assertEqual(self._errors(make_schedule()), [])

    def test_events와_recurring이_없어도_통과(self):
        self.assertEqual(self._errors({"schema_version": 1, "part": "고객서비스파트"}), [])

    def test_schema_version이_다르면_거부(self):
        s = make_schedule()
        s["schema_version"] = 2
        self.assertTrue(any("schema_version" in e for e in self._errors(s)))

    def test_kind는_여섯_값만(self):
        s = make_schedule()
        s["events"][0]["kind"] = "회식"
        self.assertTrue(any("events[0].kind" in e for e in self._errors(s)))

    def test_date_형식이_틀리면_거부(self):
        s = make_schedule()
        s["events"][0]["date"] = "2026-9-17"
        self.assertTrue(any("events[0].date" in e for e in self._errors(s)))

    def test_end가_date보다_빠르면_거부(self):
        s = make_schedule()
        s["events"][1]["end"] = "2026-09-16"
        self.assertTrue(any("events[1].end" in e for e in self._errors(s)))

    def test_label이_비면_거부(self):
        s = make_schedule()
        s["events"][0]["label"] = "  "
        self.assertTrue(any("events[0].label" in e for e in self._errors(s)))

    def test_링크는_거부(self):
        """일정도 프로필·프로젝트와 같은 공개 검사를 탄다 (docs/PRIVACY.md)."""
        s = make_schedule()
        s["events"][0]["note"] = "https://intra.example/회의록 참고"
        self.assertTrue(any("금지 패턴" in e for e in self._errors(s)))

    def test_weekdays_범위를_벗어나면_거부(self):
        s = make_schedule()
        s["recurring"][0]["weekdays"] = [0, 7]
        self.assertTrue(any("recurring[0].weekdays" in e for e in self._errors(s)))

    def test_weekdays가_배열이_아니면_거부(self):
        s = make_schedule()
        s["recurring"][0]["weekdays"] = 0
        self.assertTrue(any("recurring[0].weekdays" in e for e in self._errors(s)))

    def test_금지_키_거부(self):
        s = make_schedule()
        s["events"][0]["raw_quote"] = "원문 인용"
        self.assertTrue(any("금지 키" in e for e in self._errors(s)))


class ValidateChangelogTests(unittest.TestCase):
    """docs/CHANGELOG_SCHEMA.md '검증'."""

    def _errors(self, data):
        return cards_data.validate_changelog(data)

    def test_정상_변경목록은_통과(self):
        self.assertEqual(self._errors(make_changelog()), [])

    def test_card는_네_값만(self):
        c = make_changelog()
        c["entries"][0]["card"] = "일정"
        self.assertTrue(any("entries[0].card" in e for e in self._errors(c)))

    def test_summary가_비면_거부(self):
        c = make_changelog()
        c["entries"][1]["summary"] = ""
        self.assertTrue(any("entries[1].summary" in e for e in self._errors(c)))

    def test_date_형식이_틀리면_거부(self):
        c = make_changelog()
        c["entries"][2]["date"] = "9/16"
        self.assertTrue(any("entries[2].date" in e for e in self._errors(c)))

    def test_링크는_거부(self):
        c = make_changelog()
        c["entries"][0]["summary"] = "자세한 건 www.example.com 참고"
        self.assertTrue(any("금지 패턴" in e for e in self._errors(c)))

    def test_entries가_없어도_통과(self):
        self.assertEqual(self._errors({"schema_version": 1}), [])


class BusinessWindowTests(unittest.TestCase):
    """업무일 2일 창. part-wiki 의 part_schedule.py 와 같은 규칙이어야 한다."""

    def w(self, today, holidays=()):
        return cards_data.business_window(today, holidays)

    def test_목요일은_목금(self):
        self.assertEqual(self.w(THU), (THU, FRI))

    def test_금요일은_금월(self):
        self.assertEqual(self.w(FRI), (FRI, MON))

    def test_토요일은_월화(self):
        self.assertEqual(self.w(SAT), (MON, TUE))

    def test_일요일은_월화(self):
        self.assertEqual(self.w(SUN), (MON, TUE))

    def test_기준일이_휴일이면_다음_업무일부터(self):
        self.assertEqual(self.w(THU, {"2026-09-17"}), (FRI, MON))

    def test_창_안의_휴일은_건너뛴다(self):
        """목 기준인데 금이 휴일이면 목·월이 된다."""
        self.assertEqual(self.w(THU, {"2026-09-18"}), (THU, MON))

    def test_업무일_수는_인자로_바꾼다(self):
        self.assertEqual(cards_data.business_window(THU, (), 3), (THU, MON))

    def test_is_business_day(self):
        self.assertTrue(cards_data.is_business_day(THU, set()))
        self.assertFalse(cards_data.is_business_day(SAT, set()))
        self.assertFalse(cards_data.is_business_day(THU, {"2026-09-17"}))


class EventsInWindowTests(unittest.TestCase):
    """창 안의 일정만 고른다. 반복은 창 안 업무일에만 편다."""

    def labels(self, schedule, today, days=2):
        return [(e["date"], e["label"]) for e in cards_data.events_in_window(schedule, today, days)]

    def test_창_안의_하루_이벤트는_들어온다(self):
        self.assertIn(("2026-09-17", "스크럼 의제"), self.labels(make_schedule(), THU))

    def test_창_밖의_이벤트는_빠진다(self):
        s = make_schedule()
        s["events"].append({"date": "2026-09-21", "kind": "회의", "label": "다음주 회의"})
        self.assertNotIn(("2026-09-21", "다음주 회의"), self.labels(s, THU))

    def test_창_시작_전에_시작해_창_안에_끝나는_기간_이벤트는_들어온다(self):
        s = make_schedule()
        s["events"].append({"date": "2026-09-15", "end": "2026-09-17", "kind": "근태", "label": "출장"})
        self.assertIn(("2026-09-15", "출장"), self.labels(s, THU))

    def test_창보다_앞서_끝난_기간_이벤트는_빠진다(self):
        s = make_schedule()
        s["events"].append({"date": "2026-09-14", "end": "2026-09-16", "kind": "근태", "label": "지난 휴가"})
        self.assertNotIn(("2026-09-14", "지난 휴가"), self.labels(s, THU))

    def test_반복_일정은_해당_요일에_펴진다(self):
        """스크럼은 월~목이라 목요일 창(목·금)에서는 목요일 하루만 나온다."""
        got = [d for d, label in self.labels(make_schedule(), THU) if label == "스크럼"]
        self.assertEqual(got, ["2026-09-17"])

    def test_until이_지나면_펴지지_않는다(self):
        s = make_schedule()
        s["recurring"][0]["until"] = "2026-09-16"
        self.assertNotIn("스크럼", [label for _, label in self.labels(s, THU)])

    def test_from_이전에는_펴지지_않는다(self):
        s = make_schedule()
        s["recurring"][0]["from"] = "2026-09-18"
        self.assertEqual([d for d, label in self.labels(s, THU) if label == "스크럼"], [])

    def test_주말에는_반복을_펴지_않는다(self):
        """창(금~월)이 토·일을 지나가도 그 이틀에는 반복을 펴지 않는다."""
        s = make_schedule()
        s["recurring"] = [{"weekdays": [5, 6], "kind": "기타", "label": "주말 당번"}]
        self.assertNotIn("주말 당번", [label for _, label in self.labels(s, FRI)])

    def test_창_안_휴일에도_반복을_펴지_않는다(self):
        """금이 휴일이면 창은 목·월로 늘어나지만, 금요일 반복은 펴지 않는다."""
        s = make_schedule()
        s["holidays"] = ["2026-09-18"]
        s["recurring"] = [{"weekdays": [4], "kind": "마감", "label": "주간업무 마감"}]
        self.assertEqual(self.labels(s, THU), [("2026-09-17", "본부장 보고"), ("2026-09-17", "스크럼 의제")])

    def test_정렬은_날짜_시각_라벨_순(self):
        s = make_schedule()
        s["events"] = [
            {"date": "2026-09-17", "time": "14:00", "kind": "회의", "label": "나중"},
            {"date": "2026-09-17", "time": "09:00", "kind": "회의", "label": "ㄴ 같은 시각"},
            {"date": "2026-09-17", "time": "09:00", "kind": "회의", "label": "ㄱ 같은 시각"},
            {"date": "2026-09-18", "time": "09:00", "kind": "회의", "label": "다음날"},
        ]
        s["recurring"] = []
        self.assertEqual(
            self.labels(s, THU),
            [
                ("2026-09-17", "ㄱ 같은 시각"),
                ("2026-09-17", "ㄴ 같은 시각"),
                ("2026-09-17", "나중"),
                ("2026-09-18", "다음날"),
            ],
        )

    def test_정규화된_키를_돌려준다(self):
        e = cards_data.events_in_window(make_schedule(), THU)[0]
        self.assertEqual(
            sorted(e), sorted(["date", "end", "time", "kind", "label", "members", "note", "recurring", "ongoing"])
        )

    def test_창_시작_전에_시작한_기간_일정은_진행_중이다(self):
        sched = make_schedule()
        sched["events"].append({"date": "2026-09-14", "end": "2026-09-20", "kind": "근태", "label": "휴가", "members": []})
        got = {e["label"]: e for e in cards_data.events_in_window(sched, THU)}
        self.assertTrue(got["휴가"]["ongoing"])
        self.assertFalse(got["스크럼"]["ongoing"])

    def test_반복_여부가_표시된다(self):
        got = {label: e for (_, label), e in zip(self.labels(make_schedule(), THU), cards_data.events_in_window(make_schedule(), THU))}
        self.assertTrue(got["스크럼"]["recurring"])
        self.assertFalse(got["스크럼 의제"]["recurring"])

    def test_일정이_없으면_빈_목록(self):
        self.assertEqual(cards_data.events_in_window(None, THU), [])


class EntriesWithinTests(unittest.TestCase):
    """최근 7일 = 오늘 포함 7일. today-6 은 들어오고 today-7 은 빠진다."""

    def _log(self, *dates):
        return {
            "schema_version": 1,
            "entries": [{"date": d, "card": "site", "target": "", "summary": d} for d in dates],
        }

    def test_오늘_포함_7일_경계(self):
        got = cards_data.entries_within(self._log("2026-09-17", "2026-09-11", "2026-09-10"), THU)
        self.assertEqual([e["date"] for e in got], ["2026-09-17", "2026-09-11"])

    def test_미래_날짜는_빠진다(self):
        got = cards_data.entries_within(self._log("2026-09-18"), THU)
        self.assertEqual(got, [])

    def test_keep_days를_존중한다(self):
        log = self._log("2026-09-17", "2026-09-16", "2026-09-15")
        log["keep_days"] = 2
        self.assertEqual([e["date"] for e in cards_data.entries_within(log, THU)], ["2026-09-17", "2026-09-16"])

    def test_인자로_준_days가_keep_days를_이긴다(self):
        log = self._log("2026-09-17", "2026-09-16")
        log["keep_days"] = 7
        self.assertEqual([e["date"] for e in cards_data.entries_within(log, THU, 1)], ["2026-09-17"])

    def test_최신순이고_같은_날은_파일_순서를_지킨다(self):
        got = cards_data.entries_within(make_changelog(), THU)
        self.assertEqual(
            [(e["date"], e["summary"]) for e in got],
            [
                ("2026-09-17", "마일스톤 갱신"),
                ("2026-09-17", "말투 신호 갱신"),
                ("2026-09-16", "일정 카드 신설"),
            ],
        )

    def test_변경목록이_없으면_빈_목록(self):
        self.assertEqual(cards_data.entries_within(None, THU), [])


class RenderIndexTests(unittest.TestCase):
    """목록 페이지의 섹션 순서와 빈 상태. 곧 있을 일이 맨 위, 변경 이력은 맨 아래."""

    def _index(self, **kw):
        args = {
            "profiles": [make_profile()],
            "projects": [make_project()],
            "skipped": [],
            "part": "고객서비스파트",
            "built": "2026-09-17 10:00 KST",
            "generated": "2026-09-16",
            "schedule": make_schedule(),
            "changelog": make_changelog(),
            "today": THU,
        }
        args.update(kw)
        return build_site.render_index(**args)

    def test_섹션_순서는_일정_프로젝트_멤버_변경(self):
        h = self._index()
        order = [h.index(f"sec {cls}") for cls in ("sec-sched", "sec-proj", "sec-members", "sec-changes")]
        self.assertEqual(order, sorted(order))

    def test_히어로_칩에_건수가_붙는다(self):
        """이벤트 2건 + 목요일에 펴진 스크럼 1건 = 3건. 스크럼은 월~목이라 금요일에는 없다."""
        h = self._index()
        self.assertIn("<b>일정</b>3건", h)
        self.assertIn("<b>변경</b>3건", h)

    def test_일정이_없으면_빈_상태_문구(self):
        h = self._index(schedule=None)
        self.assertIn("업무일 2일 안에 잡힌 일정이 없다", h)
        self.assertIn("<b>일정</b>0건", h)

    def test_변경이_없으면_빈_상태_문구(self):
        h = self._index(changelog=None)
        self.assertIn("최근 7일간 바뀐 카드가 없다", h)
        self.assertIn("<b>변경</b>0건", h)

    def test_창_범위를_부제에_적는다(self):
        self.assertIn("9/17(목) ~ 9/18(금) · 업무일 2일", self._index())

    def test_기간_일정은_시작과_끝을_다_적고_진행_중을_표시한다(self):
        sched = make_schedule()
        sched["events"].append({"date": "2026-09-15", "end": "2026-09-18", "kind": "근태", "label": "휴가", "members": []})
        h = self._index(schedule=sched)
        self.assertIn("9/15(화)~9/18(금)", h)
        self.assertIn('<span class="on">진행 중</span>', h)

    def test_창_안_휴일은_휴무로_적는다(self):
        sched = make_schedule()
        sched["holidays"] = ["2026-09-18"]
        h = self._index(schedule=sched)
        self.assertIn("휴무: 9/18(금)", h)

    def test_오늘_날짜_그룹에_오늘_표시(self):
        self.assertIn('<span class="today">오늘</span>', self._index())

    def test_변경_대상이_카드와_같으면_상세로_링크(self):
        h = self._index()
        self.assertIn(build_site.href_for("p", make_project()), h)
        self.assertIn(build_site.href_for("m", make_profile()), h)

    def test_프로필_변경은_사람마다_한_줄로_그려진다(self):
        """뭉뚱그린 `김동준, 이강민 — 말투 신호 갱신` 대신 누구의 무엇이 움직였는지 보여야 한다."""
        log = make_changelog()
        log["entries"][1]["summary"] = "발화 35→41건 · 평균 44→40자 · 배지 확인요구 8.0배→단정 3.1배"
        h = self._index(changelog=log)
        self.assertIn(f'<a href="{build_site.href_for("m", make_profile())}">김동준</a>', h)
        self.assertIn('<span class="chsum">발화 35→41건 · 평균 44→40자 · 배지 확인요구 8.0배→단정 3.1배</span>', h)

    def test_긴_요약은_낱말_안에서_끊지_않는다(self):
        """좁은 폭에서 `발화` 가 `발`/`화` 로 갈라지면 읽을 수 없다."""
        self.assertIn("word-break:keep-all", self._index())

    def test_카드가_없는_이름은_링크하지_않는다(self):
        log = make_changelog()
        log["entries"][1]["target"] = "없는사람"
        h = self._index(changelog=log)
        self.assertIn("없는사람", h)
        self.assertNotIn('href="m/없는사람.html"', h)

    def test_반복_일정은_매주로_구분된다(self):
        self.assertIn("매주", self._index())

    def test_일정과_변경이_모두_없어도_빌드된다(self):
        h = self._index(schedule=None, changelog=None, profiles=[], projects=[])
        self.assertIn("sec-changes", h)
        self.assertIn("sec-sched", h)


class FakeGitHub:
    """경로별로 정해 둔 응답을 돌려주는 최소 클라이언트. 값이 ApiError 면 그것을 던진다."""

    def __init__(self, routes: dict[str, object]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def get(self, path: str, params: dict | None = None):
        self.calls.append(path)
        resp = self.routes.get(path, cards_data.ApiError(f"HTTP 404 {path}: Not Found"))
        if isinstance(resp, Exception):
            raise resp
        return resp, {}


class LoadRemoteTests(unittest.TestCase):
    """토큰이 저장소를 못 보면 GitHub 은 404 를 준다 — 그것을 '데이터 없음'으로 오해해 빈 사이트를 배포하지 않는다."""

    def test_저장소가_안_보이면_오류로_올린다(self):
        gh = FakeGitHub({})  # 모든 경로 404
        with self.assertRaises(cards_data.ApiError) as cm:
            cards_data.load_remote(gh, "org", "wiki", "main")
        self.assertIn("ORG_READ_TOKEN", str(cm.exception))
        self.assertIn("/repos/org/wiki", gh.calls)

    def test_저장소는_보이고_폴더만_없으면_빈_목록(self):
        gh = FakeGitHub({"/repos/org/wiki": {"name": "wiki"}})
        self.assertEqual(cards_data.load_remote(gh, "org", "wiki", "main"), [])

    def test_일정_변경_파일도_같이_받는다(self):
        """파일 하나짜리 카드도 Contents API 로 받는다. 없으면(404) 그 섹션만 빈다."""
        body = base64.b64encode(json.dumps(make_schedule(), ensure_ascii=False).encode()).decode()
        gh = FakeGitHub(
            {
                "/repos/org/wiki": {"name": "wiki"},
                "/repos/org/wiki/contents/data/schedule.json": {"encoding": "base64", "content": body},
            }
        )
        cards = cards_data.load_remote(gh, "org", "wiki", "main")
        self.assertEqual([(c.kind, c.file, c.ok) for c in cards], [("schedule", "schedule.json", True)])

    def test_404_아닌_오류는_그대로_올린다(self):
        gh = FakeGitHub({"/repos/org/wiki/contents/data/profiles": cards_data.ApiError("HTTP 401 x: Bad credentials")})
        with self.assertRaises(cards_data.ApiError) as cm:
            cards_data.load_remote(gh, "org", "wiki", "main")
        self.assertIn("HTTP 401", str(cm.exception))


class MainApiErrorTests(unittest.TestCase):
    """API 접근 실패는 체인 트레이스백이 아니라 한 줄 메시지로 끝난다 — 로그에서 원인이 바로 보여야 한다."""

    def _run_main(self, *, actions: bool) -> SystemExit:
        env = {"GH_TOKEN": "x", "GITHUB_ACTIONS": "true"} if actions else {"GH_TOKEN": "x"}
        saved = {k: os.environ.pop(k, None) for k in ("GH_TOKEN", "GITHUB_ACTIONS")}
        orig_load, orig_argv = build_site.load_remote, sys.argv
        try:
            os.environ.update(env)
            build_site.load_remote = lambda *a, **k: (_ for _ in ()).throw(cards_data.ApiError("wiki 를 읽을 수 없다 (HTTP 404)"))
            sys.argv = ["build_site.py", "--out", "/nonexistent/should-not-be-created"]
            with self.assertRaises(SystemExit) as cm:
                build_site.main()
            return cm.exception
        finally:
            build_site.load_remote, sys.argv = orig_load, orig_argv
            for k, v in saved.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v

    def test_actions_에서는_error_주석으로_올린다(self):
        e = self._run_main(actions=True)
        self.assertEqual(e.code, "::error::wiki 를 읽을 수 없다 (HTTP 404)")
        self.assertIsNone(e.__cause__)

    def test_로컬에서는_오류_접두어(self):
        e = self._run_main(actions=False)
        self.assertEqual(e.code, "오류: wiki 를 읽을 수 없다 (HTTP 404)")


class LoadLocalCardFilesTests(unittest.TestCase):
    """schedule.json·changelog.json 은 파일 하나가 카드 하나다. 없으면 없는 대로 간다."""

    def _root(self, files: dict[str, str]) -> pathlib.Path:
        root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        (root / "data" / "profiles").mkdir(parents=True)
        (root / "data" / "projects").mkdir(parents=True)
        for name, body in files.items():
            (root / "data" / name).write_text(body, encoding="utf-8")
        return root

    def test_파일이_없으면_카드도_없다(self):
        self.assertEqual(cards_data.load_local(self._root({})), [])

    def test_읽으면_kind와_file이_붙는다(self):
        root = self._root(
            {
                "schedule.json": json.dumps(make_schedule(), ensure_ascii=False),
                "changelog.json": json.dumps(make_changelog(), ensure_ascii=False),
            }
        )
        got = {c.kind: c for c in cards_data.load_local(root)}
        self.assertEqual(sorted(got), ["changelog", "schedule"])
        self.assertEqual(got["schedule"].file, "schedule.json")
        self.assertTrue(got["schedule"].ok and got["changelog"].ok)

    def test_어긋나면_그_파일만_건너뛴다(self):
        bad = make_schedule()
        bad["events"][0]["kind"] = "회식"
        root = self._root(
            {
                "schedule.json": json.dumps(bad, ensure_ascii=False),
                "changelog.json": json.dumps(make_changelog(), ensure_ascii=False),
            }
        )
        got = {c.kind: c for c in cards_data.load_local(root)}
        self.assertFalse(got["schedule"].ok)
        self.assertTrue(got["changelog"].ok)


class 달력에_없는_날짜(unittest.TestCase):
    def test_검증이_거부한다(self):
        s = make_schedule()
        s["events"][0]["date"] = "2026-09-31"
        self.assertTrue(any("달력에 없는" in e for e in cards_data.validate_schedule(s)))

    def test_창_계산이_건너뛴다(self):
        s = make_schedule()
        s["events"] = [{"date": "2026-09-31", "kind": "기타", "label": "없는 날"}]
        s["recurring"] = []
        self.assertEqual(cards_data.events_in_window(s, datetime.date(2026, 9, 28)), [])

    def test_하루짜리_end_는_비운다(self):
        s = make_schedule()
        s["events"] = [{"date": "2026-09-17", "end": "2026-09-17", "kind": "기타", "label": "하루"}]
        s["recurring"] = []
        got = cards_data.events_in_window(s, datetime.date(2026, 9, 17))
        self.assertEqual(got[0]["end"], "")


if __name__ == "__main__":
    unittest.main()
