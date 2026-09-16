#!/usr/bin/env python3
"""part-wiki 의 data/profiles·data/projects 로 GitHub Pages 용 정적 사이트를 만든다.

    python3 scripts/build_site.py --out _site --local ../part-wiki   # 토큰 없이 옆 클론으로
    GH_TOKEN=<PAT> python3 scripts/build_site.py --out _site         # Contents API 로 (워크플로)

적재(load_local/load_remote)와 스키마 검증은 cards_data.py 에 있고, 여기는 HTML 렌더링만 맡는다.

⚠️ 이 저장소는 public 이고 사이트는 GitHub Pages 로 **인터넷에 공개**된다.
그래서 위키 본문·대화 원문은 절대 싣지 않고,
카드 JSON 화이트리스트만 빌드한다 (part-wiki/docs/PRIVACY.md). 검색 엔진 색인은 noindex 로 막는다.
이모지 반응 집계는 스키마에 있어도 싣지 않는다.

표준 라이브러리만 쓴다. CSS 는 인라인이라 file:// 로 열어도 그대로 보인다.
한 건이 스키마에 어긋나면 그 파일만 건너뛰고 index 하단에 사유를 남긴다.
프로필·프로젝트가 0건이어도 사이트는 만들어진다 (빈 상태 문구만 찍힌다).
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cards_data import (  # noqa: E402
    AXES,
    ApiError,
    BANNER,
    DEFAULT_PART,
    FUN_KEYS,
    KST,
    MILESTONE_STATES,
    PROJECT_STATUS_ORDER,
    Card,
    GitHub,
    badge_short,
    load_local,
    load_remote,
    num,
    project_progress,
    str_list,
    sub,
    text,
    warn,
)

PROJECT_STATUS_CLASS = {"준비": "ps-todo", "진행중": "ps-doing", "보류": "ps-hold", "완료": "ps-done"}
MILESTONE_KO = {"done": "완료", "doing": "진행 중", "todo": "예정"}
WORK_STATE_HINTS = (
    ("완료", "ws-done"),
    ("진행", "ws-doing"),
    ("검토", "ws-doing"),
    ("대기", "ws-todo"),
    ("보류", "ws-hold"),
    ("미착수", "ws-todo"),
)
PROJECT_BANNER = "과제 페이지는 위키 요약이다. 일정·범위는 데이터 기준일 시점의 상태이며 확정이 아니다."
SIGNAL_ROWS = (
    ("utterances", "발화 수", "건"),
    ("total_chars", "총 글자 수", "자"),
    ("chat_chars", "대화만 글자 수", "자"),
    ("avg_chars", "평균 길이", "자"),
    ("avg_chat_chars", "평균 대화 길이", "자"),
    ("artifacts", "산출물 언급", "건"),
    ("active_hours", "활동 시간대", ""),
    ("confidence", "신뢰도", ""),
)
CHAT_GAP_RATIO = 2.0


# ───────────────────────────────────────────────────────────────────────── 유틸


def esc(v: object) -> str:
    """모든 카드 문자열은 여기를 거친다. 이름에 '<' 가 있어도 깨지지 않게."""
    return html.escape("" if v is None else str(v), quote=True)


def fmt_int(v: object) -> str:
    n = num(v)
    return f"{n:,.1f}" if not float(n).is_integer() else f"{int(n):,}"


def rows(v: object, key: str) -> list[dict[str, Any]]:
    """배열에서 `key` 가 채워진 객체만 남긴다 — 마일스톤·영역·담당·이력이 모두 같은 모양이다."""
    return [r for r in (v if isinstance(v, list) else []) if isinstance(r, dict) and text(r.get(key))]


def g(d: object, path: str, default: Any = None) -> Any:
    cur = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return default if cur is None else cur


# ───────────────────────────────────────────────────────────────────────── 스타일

CSS = """
:root{
  --bg:#F6F6F7; --card:#FFFFFF; --ink:#1B1F27; --ink2:#4B515C; --muted:#7A808B;
  --line:#E3E5E9; --line2:#EEF0F3; --soft:#F5F6F8;
  --brand:#F37321; --brand70:#F89B6C; --brand50:#FBB584; --brand-soft:#FFF1E8; --brand-ink:#B94F0C;
  --brand-line:#F9C9AA;
  --fun:#6E4BB8; --fun-soft:#F1ECFA; --fun-line:#D9CCF1; --fun-bg:#FAF8FE;
  --ok:#1E8A5A; --ok-soft:#E4F4EC;
  --warn:#B42323; --warn-soft:#FCEBEB; --warn-line:#F1B8B8;
  --hero-bg:#FFFFFF; --hero-ink:#1B1F27; --hero-sub:#4B515C;
  --tri-blend:multiply; --tri-opacity:.92;
  --shadow:0 1px 2px rgba(27,31,39,.04),0 8px 24px -18px rgba(27,31,39,.18);
  --focus:0 0 0 3px rgba(243,115,33,.35);
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#121417; --card:#1A1D22; --ink:#EEF0F3; --ink2:#C3C8D0; --muted:#8B929D;
    --line:#2B3037; --line2:#22262C; --soft:#1F2329;
    --brand:#FF8F45; --brand70:#F89B6C; --brand50:#FBB584; --brand-soft:#33231A; --brand-ink:#FFA66E;
    --brand-line:#5A3A26;
    --fun:#B99AF0; --fun-soft:#2A2338; --fun-line:#3E3358; --fun-bg:#1D1A26;
    --ok:#5FD39C; --ok-soft:#15291F;
    --warn:#FF8A8A; --warn-soft:#3A1E1E; --warn-line:#6A3434;
    --hero-bg:#15181C; --hero-ink:#F4F5F7; --hero-sub:#B7BDC6;
    --tri-blend:normal; --tri-opacity:.85;
    --shadow:none;
    --focus:0 0 0 3px rgba(255,143,69,.45);
  }
}
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-size:15px;line-height:1.65;
  letter-spacing:-.01em;-webkit-font-smoothing:antialiased;
  font-family:"Pretendard Variable",Pretendard,-apple-system,BlinkMacSystemFont,system-ui,
    "Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic","맑은 고딕",sans-serif}
a{color:var(--brand-ink);text-underline-offset:3px}
a:focus-visible,summary:focus-visible{outline:none;box-shadow:var(--focus);border-radius:8px}
h1,h2,h3,h4{margin:0;letter-spacing:-.03em;line-height:1.2}
p{margin:0 0 10px}
ul{margin:0;padding-left:19px}
li{margin:0 0 6px}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.92em;background:var(--soft);
  padding:1px 5px;border-radius:5px}
.num{font-variant-numeric:tabular-nums}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px 72px}

/* 히어로 — 흰 바탕에 Hanwha Orange 3톤 원. 페이지에서 유일하게 큰 색면 */
.hero{position:relative;overflow:hidden;background:var(--hero-bg);color:var(--hero-ink);
  padding:44px 0 40px;border-bottom:1px solid var(--line)}
.hero .in{position:relative;z-index:1;max-width:1080px;margin:0 auto;padding:0 20px;
  padding-right:min(38vw,380px)}
.tri{position:absolute;z-index:0;pointer-events:none;right:-70px;top:-90px;width:330px;height:330px;
  border-radius:50%;background:var(--brand);opacity:var(--tri-opacity)}
.tri::before,.tri::after{content:"";position:absolute;border-radius:50%;
  mix-blend-mode:var(--tri-blend)}
.tri::before{width:250px;height:250px;left:-150px;top:130px;background:var(--brand70)}
.tri::after{width:190px;height:190px;left:-30px;top:290px;background:var(--brand50)}
.hero-eyebrow{font-size:13.5px;color:var(--brand-ink);font-weight:700;margin-bottom:10px}
.hero-title{font-size:clamp(30px,6vw,54px);font-weight:800;letter-spacing:-.04em;line-height:1.08}
.hero-sub{font-size:15px;color:var(--hero-sub);margin-top:14px;max-width:560px;line-height:1.6}
.hero-chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:20px}
.hero-chips .chip{background:var(--soft);border:1px solid var(--line);border-radius:999px;
  padding:6px 13px;font-size:12.5px;color:var(--ink2);max-width:100%}
.hero-chips .chip b{color:var(--brand-ink);font-weight:700;margin-right:6px;font-size:11.5px}
.back{display:inline-flex;align-items:center;gap:4px;font-size:13px;color:var(--brand-ink);
  text-decoration:none;margin-bottom:18px;font-weight:600}
.back:hover{text-decoration:underline}

/* 고정 안내줄 — 브랜드 톤으로 낮춰서 경고가 아니라 전제처럼 읽히게 */
.banner{position:sticky;top:0;z-index:20;background:var(--brand-soft);color:var(--brand-ink);
  border-bottom:1px solid var(--brand-line);padding:9px 20px;font-size:12.5px;font-weight:700;
  text-align:center;line-height:1.45}
.banner span{font-weight:400;display:block;font-size:11.5px;opacity:.9;margin-top:2px}
.banner.proj{background:var(--soft);color:var(--ink2);border-bottom-color:var(--line)}

/* 섹션 */
.sec{margin:36px 0 0}
.seclabel{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:16px;
  padding-bottom:10px;border-bottom:1px solid var(--line)}
.sectag{font-size:11.5px;font-weight:700;padding:3px 10px;border-radius:999px;letter-spacing:0}
.sectitle{font-size:21px;font-weight:800;color:var(--ink)}
.secsub{margin-left:auto;font-size:12.5px;color:var(--muted);font-weight:400}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 20px;
  box-shadow:var(--shadow)}
.card+.card{margin-top:14px}
.cardtitle{font-size:12.5px;font-weight:700;color:var(--muted);margin-bottom:12px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:start}
.note{font-size:12.5px;color:var(--muted);margin-top:14px;padding-top:12px;border-top:1px solid var(--line2)}
.empty{color:var(--muted);font-size:13px;margin:0}

.sec-work{color:var(--brand-ink)}
.sec-work .card{border-left:4px solid var(--brand)}
.sec-work .sectag{background:var(--brand-soft);color:var(--brand-ink)}
.sec-fun{color:var(--fun);margin-top:44px}
.sec-fun .sectag{background:var(--fun-soft);color:var(--fun)}
.funwrap{background:var(--fun-bg);border:1px solid var(--fun-line);border-radius:20px;padding:18px}
.funwrap .card{border-color:var(--fun-line)}
.funhead{font-size:13px;color:var(--ink2);margin:0 0 16px;line-height:1.6}
.funhead b{color:var(--fun)}

/* 근거 강도 */
.st{display:inline-block;font-size:11px;font-weight:700;padding:3px 9px;border-radius:999px;
  white-space:nowrap}
.st-obs{background:var(--brand-soft);color:var(--brand-ink)}
.st-weak{background:var(--line2);color:var(--muted);border:1px solid var(--line)}
.st-none{background:var(--warn-soft);color:var(--warn)}

/* 업무 성향 5축 */
.axes{display:flex;flex-direction:column;gap:16px}
.axis-head{display:flex;align-items:baseline;gap:8px;font-size:13.5px;margin-bottom:6px}
.axis-head b{font-weight:800;font-size:14px;color:var(--ink)}
.axis-score{margin-left:auto;font-variant-numeric:tabular-nums;font-weight:800;color:var(--brand-ink)}
.axis-score i{font-style:normal;font-weight:400;color:var(--muted);font-size:11.5px}
.axis-track{position:relative;height:10px;border-radius:6px;background:var(--line2);overflow:hidden}
.axis-fill{display:block;height:100%;border-radius:6px;min-width:6px;
  background:linear-gradient(90deg,var(--brand50),var(--brand))}
.axis-track::after{content:"";position:absolute;inset:0;pointer-events:none;
  background:repeating-linear-gradient(90deg,transparent 0 calc(20% - 2px),var(--card) calc(20% - 2px) 20%)}
.axis-pole{display:flex;justify-content:space-between;gap:10px;font-size:11.5px;color:var(--muted);margin-top:6px}
.axis-pole span:last-child{text-align:right}

/* 말 걸기 */
.talk{background:var(--card);border:1px solid var(--fun-line);border-radius:16px;padding:20px;margin-bottom:14px}
.talk-h{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:4px}
.talk-h h3{font-size:clamp(17px,3.6vw,21px);font-weight:800;color:var(--fun)}
.talk-lead{font-size:13px;color:var(--muted);margin:0 0 16px}
.talk-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.talk-box{background:var(--soft);border-radius:12px;padding:14px 16px}
.talk-box.good{box-shadow:inset 4px 0 0 var(--fun)}
.talk-box.avoid{box-shadow:inset 4px 0 0 var(--warn-line)}
.talk-k{font-size:12px;font-weight:700;margin-bottom:8px}
.talk-box.good .talk-k{color:var(--fun)}
.talk-box.avoid .talk-k{color:var(--warn)}
.talk-box ul{padding-left:17px;font-size:13.5px}
.talk-meta{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}
.talk-time{background:var(--fun-soft);border-radius:12px;padding:14px 16px}
.talk-time .talk-k{color:var(--fun)}
.talk-time .v{font-size:clamp(15px,3vw,18px);font-weight:800;color:var(--fun);
  font-variant-numeric:tabular-nums;line-height:1.25}
.talk-ex{background:var(--soft);border-radius:12px;padding:14px 16px}
.talk-ex .talk-k{color:var(--ink2)}
.talk-ex .q{font-size:13.5px;color:var(--ink);line-height:1.6;margin:0}
.talk-ex .q::before{content:"\\201C"}
.talk-ex .q::after{content:"\\201D"}
.fun3{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}
.funcard{background:var(--card);border:1px solid var(--fun-line);border-radius:14px;padding:18px}
.funk{font-size:12.5px;color:var(--muted);font-weight:700}
.funval{font-size:clamp(24px,5vw,30px);font-weight:800;margin:4px 0 10px;line-height:1.15;
  color:var(--fun);letter-spacing:-.03em}
.funbasis{font-size:12.5px;color:var(--ink2);margin-top:10px;line-height:1.55}

/* 멤버 목록 카드 */
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,240px),1fr));gap:14px}
.mcard{position:relative;display:block;background:var(--card);border:1px solid var(--line);border-radius:18px;
  padding:20px 20px 18px;text-decoration:none;color:inherit;box-shadow:var(--shadow);
  transition:border-color .15s,transform .15s}
.mcard::before{content:"";position:absolute;left:20px;right:20px;top:0;height:3px;border-radius:0 0 3px 3px;
  background:var(--brand);opacity:0;transition:opacity .15s}
.mcard:hover{border-color:var(--brand70);transform:translateY(-1px)}
.mcard:hover::before{opacity:1}
.mcard.low{border-style:dashed}
.mname{font-size:21px;font-weight:800;line-height:1.2;letter-spacing:-.03em}
.mrole{font-size:12.5px;color:var(--muted);margin-top:4px;font-weight:600}
.mnick{font-size:13.5px;color:var(--brand-ink);margin-top:10px;font-weight:700;line-height:1.45}
.mchips{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}
.mchip{font-size:11.5px;background:var(--soft);border:1px solid var(--line);border-radius:999px;
  padding:3px 10px;color:var(--ink2)}
.mchip b{font-weight:800;color:var(--fun)}
.mchip.mbti{background:var(--fun-soft);border-color:var(--fun-soft);color:var(--fun);font-weight:800}
.mchip.age{border-color:var(--fun-line);color:var(--fun);font-weight:700}
.mchip.age i{font-style:normal;font-weight:600;font-size:10.5px;opacity:.75;margin-right:5px}
.mchip.badge{border-style:dashed;border-color:var(--fun-line);color:var(--fun)}
.lowbadge{display:flex;align-items:center;gap:6px;margin-top:12px;background:var(--warn-soft);
  color:var(--warn);border-radius:10px;padding:7px 10px;font-size:11.5px;font-weight:700;line-height:1.35}
.sec-members{color:var(--ink);margin-top:32px}
.sec-members .sectag{background:var(--brand-soft);color:var(--brand-ink)}

/* 프로젝트 */
.sec-proj{color:var(--ink);margin-top:44px}
.sec-proj .sectag{background:var(--soft);color:var(--ink2);border:1px solid var(--line)}
.sec-proj .card{border-left:4px solid var(--brand)}
.pcards{display:grid;grid-template-columns:1fr;gap:18px}
.pcard{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:26px;background:var(--card);
  border:1px solid var(--line);border-radius:20px;padding:26px 28px;text-decoration:none;color:inherit;
  box-shadow:var(--shadow);transition:border-color .15s}
.pcard:hover{border-color:var(--brand70)}
.pmain{display:flex;flex-direction:column;min-width:0}
.paside{min-width:0;border-left:1px solid var(--line2);padding-left:26px}
.phead{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.pphase{font-size:12.5px;color:var(--muted);font-weight:600}
.pname{font-size:clamp(22px,3.4vw,30px);font-weight:800;line-height:1.2;color:var(--ink);letter-spacing:-.035em}
.pcode{font-size:11.5px;color:var(--muted);font-weight:700;margin-left:8px;letter-spacing:.04em}
.ptag{font-size:14px;color:var(--brand-ink);font-weight:700;margin-top:8px}
.psum{font-size:14px;color:var(--ink2);margin-top:10px;line-height:1.65}
.pnext{font-size:13.5px;color:var(--ink);margin-top:16px;font-weight:700;line-height:1.45}
.pnext i{font-style:normal;font-weight:700;font-size:11px;color:var(--brand-ink);margin-right:8px;
  background:var(--brand-soft);padding:2px 8px;border-radius:999px}
.pk{font-size:12.5px;font-weight:700;color:var(--muted);margin:0 0 8px}
.paside .ms{margin-top:0}
.paside .ms li{font-size:13px;padding-bottom:9px}
.paside .mems{margin-top:14px}
.paside .mem{padding:6px 10px;font-size:12.5px}
.ptarget{font-size:12.5px;color:var(--muted);margin-top:12px}
.ptarget b{color:var(--ink2)}
.pcard .mchips{margin-top:12px}
.mchip.proj{background:var(--brand-soft);border-color:var(--brand-soft);color:var(--brand-ink);font-weight:700}
.ps{display:inline-block;font-size:11px;font-weight:800;padding:3px 10px;border-radius:999px;white-space:nowrap}
.ps-doing{background:var(--brand);color:#fff}
.ps-todo{background:var(--line2);color:var(--muted);border:1px solid var(--line)}
.ps-hold{background:var(--warn-soft);color:var(--warn)}
.ps-done{background:var(--ok-soft);color:var(--ok)}
.prog{position:relative;height:8px;border-radius:5px;background:var(--line2);overflow:hidden;margin-top:14px}
.prog span{display:block;height:100%;border-radius:5px;min-width:3px;
  background:linear-gradient(90deg,var(--brand70),var(--brand))}
.prog.zero span{display:none}
.progk{display:flex;justify-content:space-between;gap:10px;font-size:12px;color:var(--muted);
  margin-top:6px;font-variant-numeric:tabular-nums}
.progk b{color:var(--brand-ink);font-weight:800}
.ms{list-style:none;padding:0;margin:14px 0 0;position:relative}
.ms::before{content:"";position:absolute;left:7px;top:6px;bottom:6px;width:2px;background:var(--line)}
.ms li{position:relative;padding:0 0 12px 26px;margin:0;font-size:13.5px;line-height:1.45}
.ms li:last-child{padding-bottom:0}
.ms li::before{content:"";position:absolute;left:1px;top:4px;width:14px;height:14px;border-radius:50%;
  background:var(--card);border:2px solid var(--line)}
.ms li.done::before{background:var(--brand);border-color:var(--brand)}
.ms li.done::after{content:"";position:absolute;left:5px;top:7px;width:4px;height:7px;
  border:solid #fff;border-width:0 2px 2px 0;transform:rotate(45deg)}
.ms li.doing::before{border-color:var(--brand);border-width:3px;background:var(--card);
  box-shadow:0 0 0 3px var(--brand-soft)}
.ms li.doing{font-weight:800;color:var(--brand-ink)}
.ms li.todo{color:var(--muted)}
.ms .d{display:inline-block;min-width:88px;font-variant-numeric:tabular-nums;color:var(--muted);
  font-size:12px;font-weight:400;margin-right:6px}
.ms .k{font-size:11px;font-weight:700;margin-left:8px;color:var(--muted)}
.ws{display:inline-block;font-size:11px;font-weight:700;padding:2px 9px;border-radius:999px;
  white-space:nowrap;background:var(--line2);color:var(--ink2)}
.ws-done{background:var(--ok-soft);color:var(--ok)}
.ws-doing{background:var(--brand-soft);color:var(--brand-ink)}
.ws-todo{background:var(--line2);color:var(--muted)}
.ws-hold{background:var(--warn-soft);color:var(--warn)}
td.area{font-weight:800;white-space:nowrap;color:var(--ink)}
.mems{display:flex;flex-wrap:wrap;gap:8px}
.mem{display:inline-flex;align-items:baseline;gap:7px;background:var(--soft);border:1px solid var(--line);
  border-radius:12px;padding:8px 12px;text-decoration:none;color:var(--ink);font-size:13.5px;font-weight:800}
a.mem:hover{border-color:var(--brand70);color:var(--brand-ink)}
.mem i{font-style:normal;font-weight:400;font-size:12px;color:var(--muted)}
.mem.noprofile{opacity:.7}
.recent td.d{white-space:nowrap;font-variant-numeric:tabular-nums;color:var(--muted);width:1%}

/* 관측 신호 접기 */
details.sig{margin-top:36px;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:0 20px}
details.sig>summary{cursor:pointer;padding:15px 0;font-size:13.5px;font-weight:700;color:var(--ink2);list-style:none}
details.sig>summary::-webkit-details-marker{display:none}
details.sig>summary::before{content:"";display:inline-block;width:6px;height:6px;margin:0 10px 2px 2px;
  border:solid var(--brand);border-width:0 2px 2px 0;transform:rotate(-45deg);transition:transform .15s}
details.sig[open]>summary::before{transform:rotate(45deg)}
details.sig>div{padding-bottom:18px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line2);vertical-align:top}
th{color:var(--muted);font-weight:700;font-size:12px;white-space:nowrap}
td.n{font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}
.tscroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.gap{display:inline-block;margin-left:8px;font-size:11px;font-weight:700;padding:2px 8px;
  border-radius:999px;background:var(--brand-soft);color:var(--brand-ink);white-space:nowrap}
.warnbox{background:var(--warn-soft);border:1px solid var(--warn-line);border-radius:14px;
  padding:16px 18px;color:var(--warn);font-size:13px}
.warnbox h3{font-size:14px;margin-bottom:8px}
.warnbox p{margin:0}
.warnbox li{color:var(--warn)}
.lowwarn{margin-top:28px}
.skips{margin-top:36px}
footer{margin-top:52px;padding-top:20px;border-top:1px solid var(--line);font-size:12.5px;
  color:var(--muted);line-height:1.65}

@media (prefers-reduced-motion:reduce){
  .mcard,.pcard,.mcard::before,details.sig>summary::before{transition:none}
  .mcard:hover{transform:none}
}
@media (max-width:720px){
  .hero{padding:32px 0 30px}
  .hero .in{padding-right:20px}
  .tri{width:170px;height:170px;right:-50px;top:-70px;opacity:.45}
  .tri::before{width:120px;height:120px;left:-80px;top:70px}
  .tri::after{width:90px;height:90px;left:-10px;top:140px}
  .grid2,.talk-grid,.talk-meta{grid-template-columns:1fr}
  .fun3{grid-template-columns:1fr}
  .pcard{grid-template-columns:1fr;gap:18px;padding:20px}
  .paside{border-left:0;padding-left:0;border-top:1px solid var(--line2);padding-top:18px}
}
@media (max-width:430px){
  body{font-size:14.5px}
  .wrap{padding:0 16px 52px}
  .hero .in{padding:0 16px}
  .banner{padding:9px 16px;font-size:11.5px}
  .funwrap{padding:14px}
  .card,.talk,.mcard,.pcard{padding:16px}
  .secsub{margin-left:0;width:100%}
  .ms .d{display:block;min-width:0;margin:0}
}
"""


# ───────────────────────────────────────────────────────────────────────── 조각


def html_doc(title: str, body: str) -> str:
    return (
        '<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<meta name="robots" content="noindex,nofollow">\n'
        '<meta name="color-scheme" content="light dark">\n'
        f"<title>{esc(title)}</title>\n<style>{CSS}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def banner_html() -> str:
    return (
        f'<div class="banner">{esc(BANNER)}'
        "<span>업무 성향만 관측된 행동에 근거한다. 인사 평가나 줄세우기에 쓰지 않는다.</span></div>"
    )


def project_banner_html() -> str:
    return (
        f'<div class="banner proj">{esc(PROJECT_BANNER)}'
        "<span>상세 근거·검토 항목은 위키 본문에 있고 이 사이트에는 싣지 않는다.</span></div>"
    )


def sec(cls: str, tag: str, title: str, body: str, subtitle: str = "") -> str:
    subhtml = f'<span class="secsub">{esc(subtitle)}</span>' if subtitle else ""
    return (
        f'<section class="sec {cls}"><div class="seclabel"><span class="sectag">{esc(tag)}</span>'
        f'<h2 class="sectitle">{esc(title)}</h2>{subhtml}</div>{body}</section>'
    )


def card(title: str, body: str) -> str:
    head = f'<div class="cardtitle">{esc(title)}</div>' if title else ""
    return f'<div class="card">{head}{body}</div>'


def ul(items: object, empty: str = "적어 두지 않았습니다") -> str:
    xs = str_list(items)
    if not xs:
        return f'<p class="empty">{esc(empty)}</p>'
    return "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in xs) + "</ul>"


def strength_badge(s: object) -> str:
    t = text(s)
    flat = re.sub(r"\s+", "", t)
    cls = "st-none" if ("없음" in flat or "무작위" in flat) else ("st-weak" if t.startswith("약") else "st-obs")
    return f'<span class="st {cls}">근거 강도 · {esc(t or "미기재")}</span>'


def axes_html(axes: object) -> str:
    if not isinstance(axes, dict) or not axes:
        return '<p class="empty">축 데이터가 없습니다</p>'
    rows_html = []
    for key, ko, lo, hi in AXES:
        if key not in axes:
            continue
        v = max(1.0, min(5.0, float(num(axes.get(key)))))
        pct = (v - 1) / 4 * 100
        rows_html.append(
            f'<div class="axis"><div class="axis-head"><b>{esc(ko)}</b>'
            f'<span class="axis-score num">{v:g}<i>/5</i></span></div>'
            f'<div class="axis-track"><span class="axis-fill" style="width:{max(pct, 4):.1f}%"></span></div>'
            f'<div class="axis-pole"><span>1 · {esc(lo)}</span><span>{esc(hi)} · 5</span></div></div>'
        )
    return f'<div class="axes">{"".join(rows_html)}</div>' if rows_html else '<p class="empty">축 데이터가 없습니다</p>'


def talk_html(talk: object) -> str:
    if not isinstance(talk, dict) or not talk:
        return ""
    good = ul(talk.get("good"), "아직 정리된 요청 방식이 없습니다")
    avoid = ul(talk.get("avoid"), "특별히 피할 방식은 적혀 있지 않습니다")
    best, example = text(talk.get("best_time")), text(talk.get("example"))
    blocks = []
    if best:
        blocks.append(f'<div class="talk-time"><div class="talk-k">말 걸기 좋은 시간</div><div class="v num">{esc(best)}</div></div>')
    if example:
        blocks.append(f'<div class="talk-ex"><div class="talk-k">이렇게 보내면 된다</div><p class="q">{esc(example)}</p></div>')
    meta = f'<div class="talk-meta">{"".join(blocks)}</div>' if blocks else ""
    return (
        '<div class="talk"><div class="talk-h"><h3>이렇게 말 걸면 통한다</h3>'
        f'{strength_badge("관측된 응답 패턴 기반 · 참고용")}</div>'
        '<p class="talk-lead">집계된 말투·활동 시간대에서 뽑았다. 성격 판정이 아니라 요청 방식 제안이다.</p>'
        f'<div class="talk-grid"><div class="talk-box good"><div class="talk-k">통하는 방식</div>{good}</div>'
        f'<div class="talk-box avoid"><div class="talk-k">피하면 좋은 방식</div>{avoid}</div></div>{meta}</div>'
    )


def signals_html(sig: dict[str, Any]) -> str:
    if not sig:
        return ""
    badges: dict[str, str] = {}
    has_chat = sig.get("avg_chat_chars") is not None
    a_all, a_chat = num(sig.get("avg_chars")), num(sig.get("avg_chat_chars"))
    if a_all > 0 and a_chat > 0 and a_all >= a_chat * CHAT_GAP_RATIO:
        badges["avg_chat_chars"] = f'<span class="gap">문서 빼면 {a_all / a_chat:.1f}배 짧다</span>'
    trs = []
    for key, ko, unit in SIGNAL_ROWS:
        v = sig.get(key)
        if v is None:
            continue
        extra = badges.get(key, "")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            cell = f'<td class="n">{esc(fmt_int(v))}{esc(unit)}{extra}</td>'
        else:
            cell = f"<td>{esc(v)}{extra}</td>"
        trs.append(f"<tr><th>{esc(ko)}</th>{cell}</tr>")
    markers = sig.get("markers")
    if isinstance(markers, dict) and markers:
        pairs = sorted(markers.items(), key=lambda kv: num(kv[1]), reverse=True)
        trs.append(f'<tr><th>말투 마커</th><td>{" · ".join(f"{esc(k)} {esc(fmt_int(v))}" for k, v in pairs)}</td></tr>')
    endings = str_list(sig.get("endings_top"), 8)
    if endings:
        trs.append(f'<tr><th>자주 쓰는 어미</th><td>{esc(" · ".join(endings))}</td></tr>')
    if not trs:
        return ""
    chat_note = "<b>평균 길이</b>에는 공유한 문서·인용문이 포함된다. <b>평균 대화 길이</b>는 그것을 뺀 값이다. " if has_chat else ""
    return (
        '<details class="sig"><summary>관측 신호 (집계 수치)</summary><div>'
        f'<div class="tscroll"><table>{"".join(trs)}</table></div>'
        f'<div class="note">{chat_note}원문 인용은 담지 않는다. 건수·비율 같은 집계값만 남긴다 (docs/PRIVACY.md).</div></div></details>'
    )


def footer_html(part: str, built: str, sources: object = None) -> str:
    items = str_list(sources)
    src = f'<p>출처 — {esc(" · ".join(items))}</p>' if items else ""
    return (
        f"<footer><p>{esc(part)} · 빌드 {esc(built)}</p>{src}"
        "<p>표본은 파트 텔레그램 방에서 집계한 것이 전부다. 발화가 적은 사람의 프로필을 데이터가 많은 사람과 같은 무게로 비교하지 않는다.</p>"
        "<p>공개 범위와 금지 패턴은 part-wiki 의 docs/PRIVACY.md · 스키마는 docs/PROFILE_SCHEMA.md · docs/PROJECT_SCHEMA.md 를 따른다. "
        "재미 코너에서 빠지고 싶으면 본인 JSON 의 <code>fun</code> 을 <code>null</code> 로 두면 된다.</p></footer>"
    )


# ───────────────────────────────────────────────────────────────── 멤버 페이지


def render_person(d: dict[str, Any], built: str) -> str:
    name, part, role = text(d.get("name")), text(d.get("part")) or DEFAULT_PART, text(d.get("role"))
    generated = text(d.get("generated"))
    profile, sig = sub(d, "profile"), sub(d, "signals")
    fun_raw = d.get("fun")
    fun: dict[str, Any] | None = fun_raw if isinstance(fun_raw, dict) else None
    nick = text(fun.get("nickname")) if fun else ""
    conf, utter = text(sig.get("confidence")), sig.get("utterances")

    chips = []
    if role:
        chips.append(f'<span class="chip"><b>직무</b>{esc(role)}</span>')
    if generated:
        chips.append(f'<span class="chip"><b>데이터 기준</b>{esc(generated)}</span>')
    if conf:
        chips.append(
            f'<span class="chip"><b>신뢰도</b>{esc(conf)}'
            + (f" · 발화 {esc(fmt_int(utter))}건" if utter is not None else "")
            + "</span>"
        )
    hero = (
        '<header class="hero"><span class="tri" aria-hidden="true"></span><div class="in"><a class="back" href="../index.html">← 멤버 목록</a>'
        f'<div class="hero-eyebrow">{esc(part)}</div><h1 class="hero-title">{esc(name)}</h1>'
        + (f'<div class="hero-sub">{esc(nick)}</div>' if nick else "")
        + (f'<div class="hero-chips">{"".join(chips)}</div>' if chips else "")
        + "</div></header>"
    )

    lowwarn = ""
    if conf == "낮음":
        n = fmt_int(utter) if utter is not None else "?"
        lowwarn = (
            f'<div class="warnbox lowwarn"><h3>⚠ 표본 {esc(n)}건 — 참고만</h3>'
            "<p>발화가 적어 아래 내용의 근거가 약하다. 데이터가 많은 사람과 같은 무게로 읽지 않는다.</p></div>"
        )

    axes_note = ""
    if sub(profile, "axes"):
        axes_note = (
            '<div class="note">점수는 아래 <b>관측 신호</b>의 말투 마커에서 뽑은 것이 아니다. '
            "무엇을 먼저 정리했는지, 어떤 산출물을 냈는지 같은 <b>행동</b>을 보고 매겼다.</div>"
        )
    work_style = text(profile.get("work_style"))
    if not profile:
        work_body = card("", '<p class="empty" style="margin:0">아직 발화가 적어 업무 성향을 적지 않았다. 대화가 쌓이면 근거를 달아 채운다.</p>')
    else:
        work_body = (
            card("업무 성향 5축", axes_html(profile.get("axes")) + axes_note)
            + '<div class="grid2" style="margin-top:13px">'
            + card("일하는 방식", f'<p style="margin:0">{esc(work_style)}</p>' if work_style else '<p class="empty">아직 적혀 있지 않습니다</p>')
            + card("강점", ul(profile.get("strengths")))
            + "</div>"
        )
    s_work = sec("sec-work", "관측 근거 있음", "업무 성향", work_body, "실제 업무 참고에 쓸 수 있는 수준")

    if fun:
        fcards = []
        for key, ko in FUN_KEYS:
            blk = sub(fun, key)
            fcards.append(
                f'<div class="funcard"><div class="funk">{esc(ko)}</div>'
                f'<div class="funval">{esc(text(blk.get("value")) or "-")}</div>{strength_badge(blk.get("strength"))}'
                f'<div class="funbasis">{esc(text(blk.get("basis")) or "근거 메모 없음")}</div></div>'
            )
        fun_body = (
            '<div class="funwrap"><p class="funhead">MBTI·나이대는 <b>추측</b>이다. 위 업무 성향과 같은 근거로 쓰이지 않았다. '
            "말투 뱃지는 <b>집계한 관측값</b>이다. 항목마다 <b>근거 강도</b>를 함께 본다.</p>"
            + talk_html(fun.get("how_to_talk"))
            + f'<div class="fun3">{"".join(fcards)}</div></div>'
        )
        s_fun = sec("sec-fun", "추측 · 재미용", "재미 코너", fun_body, "근거 강도를 항목마다 표시한다")
    elif "fun" in d:
        s_fun = sec("sec-fun", "비공개", "재미 코너", card("", '<p class="empty" style="margin:0">본인 요청으로 재미 코너를 싣지 않는다. 업무 성향만 표시한다.</p>'))
    else:
        s_fun = sec("sec-fun", "아직 없음", "재미 코너", card("", '<p class="empty" style="margin:0">표본이 적어 아직 만들지 않았다. 대화가 쌓이면 채운다.</p>'))

    body = hero + banner_html() + '<main class="wrap">' + lowwarn + s_work + s_fun + signals_html(sig) + footer_html(part, built, d.get("sources")) + "</main>"
    return html_doc(f"{name} · {part} 프로필", body)


def member_card(d: dict[str, Any], href: str) -> str:
    name, role = text(d.get("name")), text(d.get("role"))
    fun_raw = d.get("fun")
    fun: dict[str, Any] | None = fun_raw if isinstance(fun_raw, dict) else None
    sig = sub(d, "signals")
    low = text(sig.get("confidence")) == "낮음"
    nick = text(fun.get("nickname")) if fun else ""
    chips = []
    if fun and text(g(fun, "mbti.value")):
        chips.append(f'<span class="mchip mbti">{esc(g(fun, "mbti.value"))}</span>')
    if fun and text(g(fun, "age_band.value")):
        chips.append(
            f'<span class="mchip age" title="나이대 추정 · 근거 약함 · {esc(g(fun, "age_band.basis", ""))}">'
            f'<i>나이대</i>{esc(g(fun, "age_band.value"))}</span>'
        )
    bc = badge_short(sig.get("badge"))
    if bc:
        chips.append(f'<span class="mchip badge" title="{esc(g(fun, "speech_badge.value", "") if fun else "")}">{esc(bc)}</span>')
    if not fun:
        chips.append('<span class="mchip">재미 코너 비공개</span>' if "fun" in d else '<span class="mchip">아직 표본 부족</span>')
    badge = ""
    if low:
        n = fmt_int(sig.get("utterances")) if sig.get("utterances") is not None else "?"
        badge = f'<div class="lowbadge">⚠ 표본 {esc(n)}건 — 참고만</div>'
    return (
        f'<a class="mcard{" low" if low else ""}" href="{esc(href)}"><div class="mname">{esc(name)}</div>'
        + (f'<div class="mrole">{esc(role)}</div>' if role else "")
        + (f'<div class="mnick">{esc(nick)}</div>' if nick else "")
        + (f'<div class="mchips">{"".join(chips)}</div>' if chips else "")
        + badge
        + "</a>"
    )


# ─────────────────────────────────────────────────────────────── 프로젝트 페이지


def status_badge(status: str) -> str:
    return f'<span class="ps {PROJECT_STATUS_CLASS.get(status, "ps-todo")}">{esc(status or "상태 미기재")}</span>'


def work_state_chip(state: object) -> str:
    s = text(state)
    if not s:
        return ""
    cls = next((c for word, c in WORK_STATE_HINTS if word in s), "")
    return f'<span class="ws {cls}">{esc(s)}</span>'


def progress_html(milestones: object, compact: bool = False) -> str:
    done, total, nxt = project_progress(milestones)
    if total == 0:
        return ""
    bar = f'<div class="prog{" zero" if done == 0 else ""}"><span style="width:{done / total * 100:.1f}%"></span></div>'
    right = f"다음 · {esc(nxt)}" if (nxt and not compact) else ""
    return bar + f'<div class="progk"><span><b>마일스톤 {done}/{total}</b> 완료</span><span>{right}</span></div>'


def milestones_html(milestones: object) -> str:
    items = rows(milestones, "label")
    if not items:
        return '<p class="empty">마일스톤이 아직 없습니다</p>'
    lis = []
    for m in items:
        st = text(m.get("state"))
        st = st if st in MILESTONE_STATES else "todo"
        lis.append(f'<li class="{st}"><span class="d">{esc(text(m.get("date")))}</span>{esc(m.get("label"))}<span class="k">{esc(MILESTONE_KO[st])}</span></li>')
    return f'<ul class="ms">{"".join(lis)}</ul>'


def workstreams_html(ws: object) -> str:
    items = rows(ws, "area")
    if not items:
        return '<p class="empty">영역별 현황이 아직 없습니다</p>'
    trs = "".join(f'<tr><td class="area">{esc(r.get("area"))}</td><td>{work_state_chip(r.get("state"))}</td><td>{esc(text(r.get("note")))}</td></tr>' for r in items)
    return f'<div class="tscroll"><table><thead><tr><th>영역</th><th>상태</th><th>메모</th></tr></thead><tbody>{trs}</tbody></table></div>'


def members_html(members: object, member_hrefs: dict[str, str], prefix: str) -> str:
    items = rows(members, "name")
    if not items:
        return '<p class="empty">담당이 아직 적혀 있지 않습니다</p>'
    chips = []
    for m in items:
        name, role = text(m.get("name")), text(m.get("role"))
        inner = esc(name) + (f"<i>{esc(role)}</i>" if role else "")
        href = member_hrefs.get(name)
        chips.append(f'<a class="mem" href="{esc(prefix + href)}">{inner}</a>' if href else f'<span class="mem noprofile" title="프로필 카드 없음">{inner}</span>')
    return f'<div class="mems">{"".join(chips)}</div>'


def recent_html(recent: object) -> str:
    items = rows(recent, "note")
    if not items:
        return '<p class="empty">최근 변화가 아직 없습니다</p>'
    trs = "".join(f'<tr><td class="d">{esc(text(r.get("date")))}</td><td>{esc(r.get("note"))}</td></tr>' for r in items)
    return f'<div class="tscroll"><table class="recent"><tbody>{trs}</tbody></table></div>'


def render_project(d: dict[str, Any], built: str, member_hrefs: dict[str, str]) -> str:
    name = text(d.get("name"))
    title = text(d.get("title")) or name
    part = text(d.get("part")) or DEFAULT_PART
    status, phase, target = text(d.get("status")), text(d.get("phase")), text(d.get("target"))
    codename, generated = text(d.get("codename")), text(d.get("generated"))
    summary, tagline = text(d.get("summary")), text(d.get("tagline"))
    members = d.get("members") if isinstance(d.get("members"), list) else []

    chips = [f'<span class="chip"><b>상태</b>{esc(status)}</span>']
    for label, v in (("단계", phase), ("목표", target), ("코드명", codename)):
        if v:
            chips.append(f'<span class="chip"><b>{label}</b>{esc(v)}</span>')
    if members:
        chips.append(f'<span class="chip"><b>담당</b>{len(members)}명</span>')
    if generated:
        chips.append(f'<span class="chip"><b>데이터 기준</b>{esc(generated)}</span>')
    hero = (
        '<header class="hero"><span class="tri" aria-hidden="true"></span><div class="in"><a class="back" href="../index.html#projects">← 목록</a>'
        f'<div class="hero-eyebrow">프로젝트 · {esc(part)}</div><h1 class="hero-title">{esc(title)}</h1>'
        + (f'<div class="hero-sub">{esc(tagline or summary)}</div>' if (tagline or summary) else "")
        + f'<div class="hero-chips">{"".join(chips)}</div></div></header>'
    )
    intro = card("한 줄 정의", f'<p style="margin:0">{esc(summary)}</p>') if (tagline and summary) else ""
    s_prog = sec(
        "sec-proj", "위키 요약", "진행 상황",
        card("진행률", progress_html(d.get("milestones")) or '<p class="empty">마일스톤이 없어 진행률을 계산하지 않는다</p>')
        + f'<div style="margin-top:13px">{card("마일스톤", milestones_html(d.get("milestones")))}</div>',
        "완료한 마일스톤 수로만 계산한다",
    )
    s_work = sec("sec-proj", "영역별", "지금 어디까지 왔나", card("", workstreams_html(d.get("workstreams"))), "데이터 기준일 시점")
    s_mem = sec("sec-proj", "담당", "누가 하나", card("", members_html(members, member_hrefs, "../")), "카드가 있는 사람은 프로필로 이어진다")
    s_next = sec("sec-proj", "다음", "다음 단계", card("", ul(d.get("next"), "다음 단계가 아직 적혀 있지 않습니다")))
    s_recent = sec("sec-proj", "이력", "최근 변화", card("", recent_html(d.get("recent"))), "최신이 위")
    body = (
        hero + project_banner_html() + '<main class="wrap">'
        + (f'<div style="margin-top:28px">{intro}</div>' if intro else "")
        + s_prog + s_work + s_mem + s_next + s_recent
        + footer_html(part, built, d.get("sources")) + "</main>"
    )
    return html_doc(f"{title} · {part} 과제", body)


def project_card(d: dict[str, Any], href: str, member_hrefs: dict[str, str] | None = None) -> str:
    """목록의 프로젝트 카드. 동시 진행 과제가 보통 2건이라 한 줄에 하나씩 크게 — 요약 전체·마일스톤·담당까지 보인다."""
    title = text(d.get("title")) or text(d.get("name"))
    status, phase, summary, codename = text(d.get("status")), text(d.get("phase")), text(d.get("summary")), text(d.get("codename"))
    tagline, target = text(d.get("tagline")), text(d.get("target"))
    members = d.get("members") if isinstance(d.get("members"), list) else []
    _, _, nxt = project_progress(d.get("milestones"))
    chips = [f'<span class="mchip proj">{esc(b)}</span>' for b in str_list(d.get("badges"), 3)]
    if members:
        chips.append(f'<span class="mchip">담당 {len(members)}명</span>')
    main = (
        f'<div class="pmain"><div class="phead">{status_badge(status)}'
        + (f'<span class="pphase">{esc(phase)}</span>' if phase else "")
        + f'</div><div class="pname">{esc(title)}'
        + (f'<span class="pcode">{esc(codename)}</span>' if codename else "")
        + "</div>"
        + (f'<div class="ptag">{esc(tagline)}</div>' if tagline else "")
        + (f'<div class="psum">{esc(summary)}</div>' if summary else "")
        + (f'<div class="mchips">{"".join(chips)}</div>' if chips else "")
        + progress_html(d.get("milestones"), compact=True)
        + (f'<div class="pnext"><i>다음</i>{esc(nxt)}</div>' if nxt else "")
        + "</div>"
    )
    # 카드 전체가 <a> 라 담당 칩은 링크 없이 이름만 (중첩 링크 금지)
    aside = (
        '<div class="paside"><div class="pk">마일스톤</div>'
        + milestones_html(d.get("milestones"))
        + (f'<div class="ptarget"><b>목표</b> {esc(target)}</div>' if target else "")
        + ('<div class="pk" style="margin-top:14px">담당</div>' + members_html(members, {}, "") if members else "")
        + "</div>"
    )
    return f'<a class="pcard" href="{esc(href)}">{main}{aside}</a>'


# ───────────────────────────────────────────────────────────────────── 목록·빌드


def render_index(profiles: list[dict[str, Any]], projects: list[dict[str, Any]], skipped: list[Card], part: str, built: str, generated: str) -> str:
    chips = [f'<span class="chip"><b>멤버</b>{len(profiles)}명</span>', f'<span class="chip"><b>프로젝트</b>{len(projects)}건</span>', f'<span class="chip"><b>빌드</b>{esc(built)}</span>']
    if generated:
        chips.append(f'<span class="chip"><b>데이터 기준</b>{esc(generated)}</span>')
    low_n = sum(1 for d in profiles if text(sub(d, "signals").get("confidence")) == "낮음")
    if low_n:
        chips.append(f'<span class="chip"><b>표본 부족</b>{low_n}명</span>')
    hero = (
        '<header class="hero"><span class="tri" aria-hidden="true"></span><div class="in"><div class="hero-eyebrow">멤버 프로필 · 프로젝트</div>'
        f'<h1 class="hero-title">{esc(part)}</h1>'
        '<div class="hero-sub">파트 텔레그램 방에서 집계한 말투 신호로 만든 파트원 카드와 진행 중인 과제 요약. '
        "위키 본문과 원본 대화는 여기에 실리지 않는다.</div>"
        f'<div class="hero-chips">{"".join(chips)}</div></div></header>'
    )
    if profiles:
        cards = f'<div class="cards">{"".join(member_card(d, href_for("m", d)) for d in profiles)}</div>'
    else:
        cards = card("", '<p class="empty" style="margin:0">아직 프로필 카드가 없다. 동기화로 신호가 쌓인 뒤 part-wiki 의 data/profiles/ 에 채운다.</p>')
    s_members = sec("sec-members", "관측 신호", "멤버", cards, "카드를 누르면 상세로")
    if projects:
        pcards = f'<div class="pcards">{"".join(project_card(d, href_for("p", d)) for d in projects)}</div>'
    else:
        pcards = card("", '<p class="empty" style="margin:0">아직 프로젝트 카드가 없다. part-wiki 의 data/projects/ 에 채운다.</p>')
    s_projects = '<div id="projects"></div>' + sec("sec-proj", "위키 요약", "프로젝트", pcards, "진행률은 마일스톤 완료 수 · 확정 계획이 아니다")
    skips = ""
    if skipped:
        items = "".join(f'<li><b>{esc(c.file)}</b> — {esc(c.errors[0] if c.errors else "빈 파일")}{esc(f" (외 {len(c.errors) - 1}건)" if len(c.errors) > 1 else "")}</li>' for c in skipped)
        skips = (
            f'<div class="warnbox skips"><h3>검증에서 건너뛴 파일 {len(skipped)}건</h3><ul>{items}</ul>'
            '<p style="margin-top:9px">한 건 때문에 전체가 막히지 않도록 그 파일만 빼고 빌드했다. 고치면 다음 빌드에 다시 들어온다.</p></div>'
        )
    body = hero + banner_html() + '<main class="wrap">' + s_members + s_projects + skips + footer_html(part, built) + "</main>"
    return html_doc(f"{part} 멤버 프로필 · 프로젝트", body)


def href_for(prefix: str, d: dict[str, Any]) -> str:
    return f"{prefix}/{quote(text(d.get('name')))}.html"


def _project_key(d: dict[str, Any]) -> tuple[int, float, str]:
    return PROJECT_STATUS_ORDER.get(text(d.get("status")), 9), num(d.get("order"), 100), text(d.get("name"))


def build(cards: list[Card], out_dir: Path) -> None:
    profiles = sorted([c.data for c in cards if c.ok and c.kind == "profile" and c.data is not None], key=lambda d: text(d.get("name")))
    projects = sorted([c.data for c in cards if c.ok and c.kind == "project" and c.data is not None], key=_project_key)
    skipped = [c for c in cards if not c.ok]
    part = next((text(d.get("part")) for d in profiles + projects if text(d.get("part"))), DEFAULT_PART)
    generated = max((text(d.get("generated")) for d in profiles + projects), default="")
    built = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

    member_hrefs = {text(d.get("name")): href_for("m", d) for d in profiles}
    (out_dir / "m").mkdir(parents=True, exist_ok=True)
    (out_dir / "p").mkdir(parents=True, exist_ok=True)
    for d in profiles:
        (out_dir / "m" / f"{text(d.get('name'))}.html").write_text(render_person(d, built), encoding="utf-8")
    for d in projects:
        (out_dir / "p" / f"{text(d.get('name'))}.html").write_text(render_project(d, built, member_hrefs), encoding="utf-8")
    (out_dir / "index.html").write_text(render_index(profiles, projects, skipped, part, built, generated), encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")  # Jekyll 후처리 방지
    print(f"{out_dir}/index.html 생성 — 멤버 {len(profiles)}명 · 프로젝트 {len(projects)}건 · 건너뜀 {len(skipped)}건", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description="part-wiki 카드 JSON 으로 GitHub Pages 정적 사이트를 만든다")
    ap.add_argument("--out", default="_site", metavar="DIR", help="빌드 결과 디렉터리 (기본 _site)")
    ap.add_argument("--local", metavar="DIR", help="part-wiki 로컬 클론 경로 (API 대신 파일을 읽는다)")
    args = ap.parse_args()

    org = os.environ.get("ORG", "customer-service-part-poc-project")
    repo = os.environ.get("WIKI_REPO", "part-wiki")
    ref = os.environ.get("WIKI_REF", "main")

    if args.local:
        cards = load_local(Path(args.local))
    else:
        token = os.environ.get("GH_TOKEN")
        if not token:
            raise SystemExit("GH_TOKEN 이 없습니다 (ORG_READ_TOKEN). 토큰 없이 확인하려면 --local DIR")
        try:
            cards = load_remote(GitHub(token), org, repo, ref)
        except ApiError as e:
            # 트레이스백 대신 한 줄로. Actions 에서는 ::error:: 로 올려 실행 요약에 바로 보이게 한다.
            raise SystemExit(f"::error::{e}" if os.environ.get("GITHUB_ACTIONS") else f"오류: {e}") from None
    for c in cards:
        if not c.ok:
            warn(f"건너뜀 {c.file}: " + " / ".join(c.errors))
    build(cards, Path(args.out))


if __name__ == "__main__":
    main()
