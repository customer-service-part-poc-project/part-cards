#!/usr/bin/env python3
"""cards_data.py 의 검증 규칙과 build_site.py 의 공개 범위를 테스트한다.

근거: part-wiki 의 docs/PROFILE_SCHEMA.md · docs/PROJECT_SCHEMA.md · docs/PRIVACY.md.
표준 라이브러리만 쓴다.

    python3 -m unittest discover -s scripts -p 'test_*.py'
"""
from __future__ import annotations

import copy
import os
import pathlib
import sys
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


if __name__ == "__main__":
    unittest.main()
