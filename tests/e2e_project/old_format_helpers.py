"""古い形式のプロジェクトファイルの見本（2026-10-20）。

今の版で保存した tools/fixtures/rich.nlmf を、古い版が書いた形へ書き換えて作る（素材のファイルは増やさない）。
形の一覧と、どの版の物かは CLAUDE.md「古い形式のプロジェクトを開く」。

- variant(name): (ファイル名, 中身の文字列, 期待する物) を返す。期待する物は {難易度の.dat名: Counter(物の鍵)}
- items(pj): 保存内容（buildProjectText を JSON にした物）から、難易度ごとに
  「フラット（今見えている物）」と「クリップの中身（開き直すと見える物＝今の形はクリップの中身が正）」の物の鍵を数える
- lost(want, got, part) / extra(want, got, part): 期待する物のうち got に無い物・got で増えた物の数（種類ごと・難易度ごと）。無ければ {}
- layout_problems(pj): クリップの並びのおかしな所（同じレーンで重なる・レーンの数の外・種類の違う中身・長さが無い）
"""
import copy
import json
import sys
from collections import Counter
from pathlib import Path

_T = Path(__file__).resolve().parents[1]
if str(_T / "e2e_nle") not in sys.path:   # NLE の操作の部品（nle_helpers）を使う
    sys.path.insert(0, str(_T / "e2e_nle"))

RICH = Path(__file__).resolve().parents[2] / "tools" / "fixtures" / "rich.nlmf"

ENC = {   # editor-app.js の _ENC と同じ並び（保存形式 v2 のタプル）
    "notes": ("note", ["beat", "x", "y", "c", "d"]),
    "bombs": ("bomb", ["beat", "x", "y"]),
    "walls": ("wall", ["beat", "x", "y", "dur", "w", "h"]),
    "arcs": ("arc", ["b", "c", "x", "y", "d", "mu", "tb", "tx", "ty", "tc", "tmu", "m"]),
    "chains": ("chain", ["b", "c", "x", "y", "d", "tb", "tx", "ty", "sc", "s"]),
    "lights": (None, ["beat", "et", "i", "f"]),
}
FLAT = {"notes": "notes", "bombs": "bombs", "walls": "walls", "arcs": "arcs", "chains": "chains", "lights": "lightEvents"}
KINDS = tuple(ENC)


def dec(arr, t):
    """タプル（v2）→ オブジェクト（v1 の形）。オブジェクトはそのまま"""
    k, fs = ENC[t]
    out = []
    for o in arr or []:
        if not isinstance(o, list):
            out.append(dict(o))
            continue
        it = {"kind": k} if k else {}
        for i, f in enumerate(fs):
            if o[i] is not None:
                it[f] = o[i]
        if len(o) > len(fs) and o[len(fs)] is not None:
            it["_tr"] = o[len(fs)]
        it["raw"] = o[len(fs) + 1] if len(o) > len(fs) + 1 else None
        out.append(it)
    return out


def key(t, o, off=0.0):
    r = lambda v: round((v or 0) + off, 4)
    if t == "notes":
        return (r(o.get("beat")), o.get("x"), o.get("y"), o.get("c"), o.get("d"))
    if t == "bombs":
        return (r(o.get("beat")), o.get("x"), o.get("y"))
    if t == "walls":
        return (r(o.get("beat")), o.get("x"), o.get("y"), o.get("dur"), o.get("w"), o.get("h"))
    if t == "arcs":
        return (r(o.get("b")), o.get("c"), o.get("x"), o.get("y"), o.get("d"), r(o.get("tb")), o.get("tx"), o.get("ty"))
    if t == "chains":
        return (r(o.get("b")), o.get("c"), o.get("x"), o.get("y"), o.get("d"), r(o.get("tb")), o.get("tx"), o.get("ty"), o.get("sc"), o.get("s"))
    return (r(o.get("beat")), o.get("et"), o.get("i"))


def _bf(t):
    return "b" if t in ("arcs", "chains") else "beat"


def items(pj):
    """{難易度の.dat名: {'flat': Counter, 'clips': Counter}}（鍵の先頭に種類）"""
    out = {}
    for st in (pj.get("difficulties") or {}).values():
        flat, clips = Counter(), Counter()
        for t in KINDS:
            for o in dec(st.get(FLAT[t]), t):
                flat[(t,) + key(t, o)] += 1
        for s in st.get("sections") or []:
            if s.get("kind") == "null":
                continue
            L, off = s.get("len") or 4, s.get("beat") or 0
            for t in KINDS:
                for o in dec((s.get("content") or {}).get(t), t):
                    if 0 <= (o.get(_bf(t)) or 0) < L:
                        clips[(t,) + key(t, o, off)] += 1
        out[st.get("name")] = {"flat": flat, "clips": clips}
    return out


def lost(want, got, part):
    """want の物のうち got[難易度][part] に無い数 {難易度: {種類: 数}}（全部あれば {}）"""
    res = {}
    for dn, w in want.items():
        g = (got.get(dn) or {}).get(part, Counter())
        miss = w - g
        if miss:
            c = Counter(k[0] for k in miss.elements())
            res[dn] = dict(sorted(c.items()))
    return res


def layout_problems(pj):
    """クリップの並びのおかしな所: 同じレーンで重なる・レーンの数の外・種類の違う中身（ノーツのクリップの中のライト等）・長さが無い"""
    out = []
    lanes = {"n": pj.get("notesLanes") or 0, "l": pj.get("lightLanes") or 0}
    for st in (pj.get("difficulties") or {}).values():
        secs = [s for s in st.get("sections") or [] if s.get("kind") != "null"]
        for s in secs:
            lk = "l" if s.get("lk") == "l" else "n"
            if not (s.get("len") or 0) > 0:
                out.append(f"{st['name']}: 長さの無いクリップ {s.get('label')}")
            if not 0 <= (s.get("track") or 0) < lanes[lk]:
                out.append(f"{st['name']}: レーンの外のクリップ {lk}{s.get('track')}（{lanes[lk]}本）")
            wrong = [t for t in KINDS if (s.get("content") or {}).get(t) and ((t == "lights") != (lk == "l"))]
            if wrong:
                out.append(f"{st['name']}: {lk} のクリップに {wrong}")
        grp = lambda s: ("l" if s.get("lk") == "l" else "n", s.get("track") or 0)
        for i, a in enumerate(secs):
            for b in secs[i + 1:]:
                if grp(a) != grp(b):
                    continue
                a0, b0 = a.get("beat") or 0, b.get("beat") or 0
                if a0 < b0 + (b.get("len") or 4) - 1e-3 and b0 < a0 + (a.get("len") or 4) - 1e-3:
                    out.append(f"{st['name']}: 同じレーンで重なるクリップ {a.get('label')}@{a0} と {b.get('label')}@{b0}")
    return out


def extra(want, got, part):
    """got にあって want に無い物の数（増えていないこと＝消した物が生き返っていないこと）"""
    res = {}
    for dn, g in got.items():
        x = g.get(part, Counter()) - want.get(dn, Counter())
        if x:
            res[dn] = dict(sorted(Counter(k[0] for k in x.elements()).items()))
    return res


# ---- 見本を作る ----
def _rich():
    return json.loads(RICH.read_text(encoding="utf-8"))


def _to_objects(pj, keep_tr=False):
    """全部の物をオブジェクトの形（保存形式 v1）へ。フラットの _tr（レーン）は v1 には無かったものとして外す"""
    for st in pj["difficulties"].values():
        for t in KINDS:
            arr = dec(st.get(FLAT[t]), t)
            if not keep_tr:
                for o in arr:
                    o.pop("_tr", None)
            st[FLAT[t]] = arr
        for s in st.get("sections") or []:
            c = s.get("content") or {}
            s["content"] = {t: dec(c.get(t), t) for t in KINDS if c.get(t)}


def _hard_to_v2dat(pj):
    """Hard を v2 の .dat の難易度にする（アークは v2 に無いので外す）"""
    st = pj["difficulties"]["hardstandard.dat"]
    st["v3"] = False
    st["base"] = {"_version": "2.2.0", "_notes": [], "_obstacles": [], "_events": [], "_waypoints": []}
    st["arcs"] = []
    for s in st.get("sections") or []:
        (s.get("content") or {}).pop("arcs", None)


def _cur_sections(pj):
    return copy.deepcopy(pj["difficulties"][pj["current"].lower()]["sections"])


def _want(pj):
    """期待する物＝見本のフラット（見本はフラットとクリップの中身が同じ物を表す。足した物はフラットにも入れる）"""
    return {st["name"]: items({"difficulties": {"x": st}})[st["name"]]["flat"] for st in pj["difficulties"].values()}


def _node_sections(st, cuts):
    """ノードの画面の頃の形: 長さ・レーン・種類(lk)の無いクリップを拍 cuts で区切り、ノーツ系とライトを同じクリップの中身に入れる"""
    bounds = list(cuts) + [None]
    secs = []
    for i, b0 in enumerate(cuts):
        b1 = bounds[i + 1]
        c = {}
        for t in KINDS:
            arr = [o for o in dec(st.get(FLAT[t]), t)
                   if (o.get(_bf(t)) or 0) >= b0 and (b1 is None or (o.get(_bf(t)) or 0) < b1)]
            for o in arr:
                o.pop("_tr", None)
                for f in ("b", "tb") if t in ("arcs", "chains") else ("beat",):
                    o[f] = (o.get(f) or 0) - b0
            if arr:
                c[t] = arr
        secs.append({"beat": b0, "label": f"Node{i + 1}", "content": c})
    return secs


VARIANTS = ("bsnm", "bslm", "v2_bare", "v1_full", "v1_top", "v1_flat", "v1_node", "v1_node2", "v2_noclips", "v2_orphans", "v2_stale")


def variant(name):
    pj = _rich()
    fname = "old.nlmf"
    if name in ("bsnm", "bslm"):   # 拡張子・format の名前だけ古い（中身は今の形）
        pj["format"] = name
        fname = "old." + name
    elif name == "v2_bare":   # 保存形式 v2 だが、レーンの数・L/S/M・テンポパート・表示位置・クロマ・INFOのノード等を持たない古い版の形
        for k in ("notesLanes", "lightLanes", "laneStates", "tempoParts", "view", "analysis", "chromaPalette",
                  "chainCurveGlobal", "njsCfg", "infoGraph", "markers", "musicSegs", "coverData"):
            pj.pop(k, None)
        for st in pj["difficulties"].values():
            for s in st["sections"]:
                for k in ("col", "id", "gid"):
                    s.pop(k, None)
    elif name.startswith("v1_"):   # 保存形式 v1（version 無し・物はオブジェクトの形）
        pj.pop("version", None)
        _hard_to_v2dat(pj)
        _to_objects(pj)
        for k in ("notesLanes", "lightLanes", "laneStates", "tempoParts", "view"):
            pj.pop(k, None)
        if name == "v1_full":     # トップレベルの sections（今の難易度の写し）＋難易度ごとの sections
            pj["sections"] = _cur_sections(pj)
        elif name == "v1_top":    # トップレベルの sections だけ（難易度ごとのクリップは無い）
            pj["sections"] = _cur_sections(pj)
            for st in pj["difficulties"].values():
                st.pop("sections", None)
        elif name == "v1_flat":   # クリップが無い（フラットだけ）
            for st in pj["difficulties"].values():
                st.pop("sections", None)
        elif name in ("v1_node", "v1_node2"):   # ノードの画面の頃: 長さ・種類の無いクリップにノーツ系もライトも入っている
            cur = pj["difficulties"][pj["current"].lower()]
            pj["sections"] = _node_sections(cur, [0] if name == "v1_node" else [0, 8])
            for st in pj["difficulties"].values():
                st.pop("sections", None)
    elif name == "v2_noclips":   # 保存形式 v2 で、今でない難易度にクリップが無い（フラットだけ）
        pj["difficulties"]["expertstandard.dat"]["sections"] = []
    elif name == "v2_orphans":   # 保存形式 v2 で、フラットにだけある物（どのクリップの範囲にも無い）
        st = pj["difficulties"]["hardstandard.dat"]
        st["notes"].append([20, 0, 0, 0, 1, 0, None])   # クリップ(0〜16拍)の外
        st["walls"].append([18, 0, 0, 1, 1, 5, 0])
        st["lightEvents"].append([20, 2, 1, 1, 0])
    elif name == "v2_stale":   # 保存形式 v2 で、クリップの範囲の中なのに中身に無い物がフラットにある＝消した物の残り（クリップの中身が正・戻さない）
        want = _want(pj)
        st = pj["difficulties"]["hardstandard.dat"]
        st["bombs"].append([5.5, 0, 2, 0])
        st["lightEvents"].append([9, 3, 5, 1, 0])
        return fname, json.dumps(pj, ensure_ascii=False), want
    else:
        raise ValueError(name)
    return fname, json.dumps(pj, ensure_ascii=False), _want(pj)
