"""画面の崩れ確認（tests/visual）の本体。画面の一覧は screens.py、ページ内の部品は vis_page.js。

1つの画面につき次をする:
  1. 場面の準備（開き直し・素材の読込・アニメーション停止）→ 画面の steps
  2. 撮影を2回して差が出ないこと（＝決定的に撮れていること）を確かめる。揺れる時は少し待って撮り直し、
     それでも揺れたら失敗（揺れる所を screens.py の hide / mask に足す）
  3. 崩れの検出（vis_page.js の layout）。許可リスト layout_allow.json・既知の崩れ layout_known.json で仕分ける
  4. 基準画像 tests/visual/baseline/<名前>.png とピクセル比較。変化した画面だけ、変化した付近を切り出した
     まとめ画像 test-out/visual/review.png（AI確認用）とレポート test-out/visual/report.html（人の確認用）を作る

■ 変化の判定（許容値）
  画素: R・G・B のどれかの差が PIX_THR（32/255）を超えたら「変化した画素」（文字のにじみ・描画の揺らぎを吸収）
  画面: 比較から除く所を除いて、変化した画素が MIN_PX（25）個以上なら「変化あり」（カーソル1本ぶん程度は無視）
  まとまり: 8px のマスに区切り、近い（32px 以内）変化をまとめて1つの領域にする。まとめ画像には大きい順に6か所まで
"""
import base64
import html
import json
import shutil
from pathlib import Path

import screens as S

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = HERE / "baseline"
OUT = ROOT / "test-out" / "visual"
CUR, BEFORE, DIFF, LAY, TMP = OUT / "current", OUT / "before", OUT / "diff", OUT / "layout", OUT / "_tmp"
PAGE_JS = (HERE / "vis_page.js").read_text(encoding="utf-8")

PIX_THR = 32        # 画素の色差（0〜255）。これを超えたら変化
MIN_PX = 25         # 変化した画素がこの数以上で「画面が変化した」
TILE, GAP = 8, 4    # 領域のまとめ方: 8pxのマス・4マス(32px)以内の変化は同じ領域
MAX_REGIONS = 6     # 1画面でまとめ画像に出す領域の数
REVIEW_W = 1800     # まとめ画像の横幅
STABLE_TRIES = 4    # 揺れた時の撮り直し回数

CMP_OPT = {"thr": PIX_THR, "tile": TILE, "gap": GAP, "maxRegions": MAX_REGIONS}


def _load_list(name):
    p = HERE / name
    if not p.exists():
        return []
    return [e for e in json.loads(p.read_text(encoding="utf-8")) if isinstance(e, dict)]


def _match(entry, issue, screen):
    if entry.get("kind") and entry["kind"] != issue["kind"]:
        return False
    scr = entry.get("screens") or ["*"]
    if "*" not in scr and screen not in scr:
        return False
    a, b = entry.get("a", ""), entry.get("b", "")
    ia, ib = issue["a"], issue["b"]
    if a in ia and b in ib:
        return True
    return issue["kind"] == "重なり" and a in ib and b in ia   # 重なりは順番を問わない


def _issue_text(i):
    s = f"{i['kind']}: {i['a']}"
    if i["b"]:
        s += f" ⇔ {i['b']}"
    x, y, w, h = i["rect"]
    return s + f"  @({x},{y} {w}×{h})" + (f"  {i['detail']}" if i["detail"] else "")


class Runner:
    """グループ内で1つ。場面を順に進めながら画面を撮り、結果を覚えておく"""

    def __init__(self, t):
        self.t = t
        self.scene = None       # いまページにある場面
        self.size = S.SIZE
        self.at = -1            # その場面の何番目の画面まで進んだか
        self.results = {}       # 画面名 → 結果
        self.changed = []       # 変化した画面名（出た順）
        self.allow = _load_list("layout_allow.json")
        self.known = _load_list("layout_known.json")
        self.index = {}
        self._tool = None       # 画像の比較・合成をする補助タブ（エディタのページは描画ループで重いので分ける）
        for sc in S.SCENES:
            for i, s in enumerate(sc.screens):
                if s.name in self.index:
                    raise ValueError(f"screens.py: 画面の名前が重複しています: {s.name}")
                self.index[s.name] = (sc, i)
        # 前回の出力を片付ける（古いまとめ画像を見てしまわないように）
        for d in (CUR, BEFORE, DIFF, LAY, TMP):
            shutil.rmtree(d, ignore_errors=True)
            d.mkdir(parents=True, exist_ok=True)
        for f in ("review.png", "report.html"):
            (OUT / f).unlink(missing_ok=True)
        BASE.mkdir(parents=True, exist_ok=True)

    # ---- 場面を進める ----
    def _start(self, sc):
        w, h = sc.size
        for attempt in range(2):
            try:
                self.t.ed.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)
                break
            except Exception:
                if attempt:
                    raise
                self.t.restart()   # ブラウザが落ちていた（前の画面の失敗など）＝起動し直す
        self.size = (w, h)
        ed = self.t.fresh(sc.fixture, settle=1.5)   # 波形などの描画が落ち着くまで待つ（撮影の揺れ確認の前に）
        self._inject(ed)
        self.scene, self.at = sc, -1
        for st in sc.setup:
            st(ed)

    def _inject(self, ed):
        if not ed.js("!!window.__vis"):
            ed.js(PAGE_JS)
        ed.js("__vis.freeze()")

    def goto(self, name):
        sc, idx = self.index[name]
        ed = self.t.ed
        if self.scene is not sc or self.at >= idx:
            self._start(sc)
            ed = self.t.ed
        try:
            while self.at < idx:
                if self.at >= 0:
                    for st in sc.screens[self.at].leave:
                        st(ed)
                self.at += 1
                for st in sc.screens[self.at].steps:
                    st(ed)
        except Exception:
            self.scene = None   # 途中で失敗した場面は、次の画面で最初からやり直す
            raise
        return sc, sc.screens[idx]

    # ---- 撮影 ----
    def _shot(self, ed, path):
        """撮ってファイルに保存し、ページから読める URL（serve.py はプロジェクトのフォルダを配信している）を返す"""
        path.write_bytes(base64.b64decode(ed.call("Page.captureScreenshot", format="png")["data"]))
        return _url(path)

    def _masks(self, ed, items):
        """比較から除く領域。セレクタはその要素の位置、(x, y, 幅, 高さ) はそのまま（x・y が負なら右端・下端から）"""
        sels = [m for m in items if isinstance(m, str)]
        out = (ed.js(f"__vis.rects({json.dumps(sels)})") or []) if sels else []
        w, h = self.size
        for m in items:
            if isinstance(m, (tuple, list)):
                x, y, mw, mh = m
                out.append([w + x if x < 0 else x, h + y if y < 0 else y, mw, mh])
        return out

    @property
    def tool(self):
        """画像を扱う補助タブ（同じEdgeの別タブ）。ブラウザを起動し直した時は開き直す"""
        ed = self.t.ed
        if self._tool is None or self._tool.editor is not ed:
            self._tool = ed.new_tab("tests/visual/blank.html")
            self._tool.js(PAGE_JS)
        return self._tool

    def _compare(self, ed, url_a, url_b, masks):
        return self.tool.js(f"__vis.compare({json.dumps(url_a)},{json.dumps(url_b)},{json.dumps(masks)},{json.dumps(CMP_OPT)})")

    def capture(self, name):
        if name in self.results:
            return self.results[name]
        sc, s = self.goto(name)
        ed = self.t.ed
        self._inject(ed)
        mx, my = s.mouse or S.MOUSE
        ed.move(mx, my)
        ed.wait(s.settle)
        hide = S.COMMON_HIDE + sc.hide + s.hide
        ed.js(f"__vis.hide({json.dumps(hide)})")
        try:
            masks = self._masks(ed, S.COMMON_MASK + sc.mask + s.mask)
            # 揺れの確認: 2回撮って同じになるまで（最大 STABLE_TRIES 回）
            shots = [TMP / f"{name}_{k}.png" for k in range(STABLE_TRIES + 1)]
            a = self._shot(ed, shots[0])
            unstable = None
            for k in range(STABLE_TRIES):
                ed.wait(0.35)
                b = self._shot(ed, shots[k + 1])
                r = self._compare(ed, a, b, masks)
                if r["n"] < MIN_PX:
                    unstable = None
                    break
                unstable = r
                a = b
                ed.wait(0.6)
            last = shots[k + 1]
            cfg = {"popups": S.COMMON_POPUPS + s.popups, "ignore": S.COMMON_IGNORE + s.ignore}
            issues = ed.js(f"__vis.layout({json.dumps(cfg)})") or []
            # 崩れの仕分け
            allowed, known, new = [], [], []
            for i in issues:
                if any(_match(e, i, name) for e in self.allow):
                    allowed.append(i)
                elif any(_match(e, i, name) for e in self.known):
                    known.append(i)
                else:
                    new.append(i)
            lay_png = None
            if new or known:
                items = [{"rect": i["rect"], "label": f"{k + 1}"} for k, i in enumerate(new + known)]
                ed.js(f"__vis.mark({json.dumps(items)})")
                lay_png = LAY / f"{name}.png"
                self._shot(ed, lay_png)
                ed.js("__vis.unmark()")
        finally:
            ed.js("__vis.hide([])")
        cur = CUR / f"{name}.png"
        shutil.copyfile(last, cur)
        res = dict(name=name, title=s.title, png=cur, masks=masks, unstable=unstable,
                   allowed=allowed, known=known, new=new, lay_png=lay_png)
        unused_known = [e for e in self.known if name in (e.get("screens") or []) and not any(_match(e, i, name) for i in issues)]
        res["fixed_known"] = unused_known
        self.results[name] = res
        return res

    # ---- テストの中身 ----
    def check_layout(self, name):
        t = self.t
        r = self.capture(name)
        if r["unstable"]:
            u = r["unstable"]
            regs = ", ".join(f"({g['x']},{g['y']} {g['w']}×{g['h']})" for g in u["regions"])
            raise AssertionError(f"同じ画面を続けて撮っても毎回変わります（変化 {u['n']}px: {regs}）。"
                                 f"揺れる所を screens.py の hide / mask に足してください")
        if r["allowed"]:
            t.info(f"許可リストに一致して無視した崩れ {len(r['allowed'])} 件")
        for e in r["fixed_known"]:
            t.info(f"既知の崩れが見当たりません（直ったなら layout_known.json から外す）: {e.get('note') or e}")
        if r["new"]:
            lines = [f"{k + 1}. {_issue_text(i)}" for k, i in enumerate(r["new"])]
            raise AssertionError(f"崩れを {len(r['new'])} 件検出（画像の番号: {r['lay_png']}）\n" + "\n".join(lines)
                                 + "\n意図した配置なら tests/visual/layout_allow.json に理由付きで足す")
        if r["known"]:
            notes = sorted({next((e.get("note", "") for e in self.known if _match(e, i, name)), "") for i in r["known"]})
            t.skip("既知の崩れ: " + " / ".join(n for n in notes if n) + f"（{len(r['known'])}件・画像 {r['lay_png']}）")

    def check_image(self, name):
        t = self.t
        r = self.capture(name)
        base = BASE / f"{name}.png"
        meta = BASE / f"{name}.json"
        if r["unstable"]:
            t.skip("撮るたびに画面が変わるため比較しません（崩れの検出の結果を参照）")
        if t.accept or not base.exists():
            shutil.copyfile(r["png"], base)
            meta.write_text(json.dumps({"masks": r["masks"]}), encoding="utf-8")
            t.info(("基準画像を更新" if base.exists() and t.accept else "基準画像を新規作成") + f": tests/visual/baseline/{name}.png")
            return
        bmasks = []
        if meta.exists():
            try:
                bmasks = json.loads(meta.read_text(encoding="utf-8")).get("masks") or []
            except Exception:
                pass
        masks = r["masks"] + bmasks
        ed = t.ed
        ua, ub = _url(base), _url(r["png"])
        cmp = self._compare(ed, ua, ub, masks)
        same_size = cmp["sizeA"] == cmp["sizeB"]
        if cmp["n"] < MIN_PX and same_size:
            if cmp["n"]:
                t.info(f"わずかな差 {cmp['n']}px（許容 {MIN_PX}px 未満）")
            return
        sub = f"変化 {cmp['n']}px・{cmp['total']}か所" + ("" if same_size else f"・大きさ {cmp['sizeA']}→{cmp['sizeB']}")
        comp = self.tool.js(f"__vis.compose({json.dumps(ua)},{json.dumps(ub)},{json.dumps(masks)},"
                     f"{json.dumps({'title': r['title'] + '（' + name + '）', 'sub': sub})},"
                     f"{json.dumps(dict(CMP_OPT, maxWidth=REVIEW_W))})")
        (DIFF / f"{name}.png").write_bytes(base64.b64decode(comp["review"]))
        (DIFF / f"{name}_full.png").write_bytes(base64.b64decode(comp["diff"]))
        shutil.copyfile(base, BEFORE / f"{name}.png")
        r["cmp"], r["sub"] = cmp, sub
        if name not in self.changed:
            self.changed.append(name)
        t.review(f"見た目が変化しました（{sub}）。意図した変化なら --accept", DIFF / f"{name}.png")

    # ---- まとめ画像とレポート ----
    def _write_outputs(self):
        if self.changed:
            parts = [_url(DIFF / f"{n}.png") for n in self.changed]
            hdr = f"見た目が変化した画面 {len(self.changed)}件（意図した変化なら tools/run_tests.py visual --accept）"
            png = self.tool.js(f"__vis.stack({json.dumps(parts)},{json.dumps({'header': hdr})})")
            (OUT / "review.png").write_bytes(base64.b64decode(png))
        (OUT / "report.html").write_text(self._report_html(), encoding="utf-8")

    def write_final(self):
        """最後に1回だけ呼ぶ（まとめ画像の合成は重いので画面ごとには作らない）。何も変化が無ければ「変化なし」のレポートにする"""
        self._write_outputs()
        lay = [n for n, r in self.results.items() if r["new"]]
        return self.changed, lay

    def _report_html(self):
        e = html.escape
        changed = [self.results[n] for n in self.changed]
        lay = [r for r in self.results.values() if r["new"] or r["known"]]
        secs = []
        for r in changed:
            n = r["name"]
            regs = "".join(f"<li>領域{k + 1}: x{g['x']} y{g['y']} {g['w']}×{g['h']}（変化 {g['n']}px）</li>"
                           for k, g in enumerate(r["cmp"]["regions"]))
            secs.append(f"""
<section class="scr" id="s_{e(n)}">
  <h2>{e(r['title'])} <small>{e(n)}</small></h2>
  <p class="sub">{e(r['sub'])}</p>
  <ul class="regs">{regs}</ul>
  <h3>変化した付近（前｜後｜差分）</h3>
  <img class="crop" src="diff/{e(n)}.png" alt="">
  <h3>画面全体 <span class="btns">
    <button data-v="before">前（基準）</button><button data-v="after" class="on">後（今回）</button><button data-v="diff">差分</button>
    <button data-v="flip">自動で切替</button></span></h3>
  <div class="viewer" data-name="{e(n)}">
    <img class="v before" src="before/{e(n)}.png" alt="">
    <img class="v after" src="current/{e(n)}.png" alt="">
    <img class="v diff" src="diff/{e(n)}_full.png" alt="">
  </div>
  <p class="slider">左右に重ねて比べる: <input type="range" min="0" max="100" value="50" class="wipe"></p>
  <div class="wipebox"><img src="current/{e(n)}.png" alt=""><div class="wipeTop"><img src="before/{e(n)}.png" alt=""></div></div>
</section>""")
        lsecs = []
        for r in lay:
            items = "".join(f"<li>{'<b>新</b> ' if i in r['new'] else '既知 '}{e(_issue_text(i))}</li>" for i in r["new"] + r["known"])
            lsecs.append(f"""<section class="scr"><h2>{e(r['title'])} <small>{e(r['name'])}</small></h2><ol>{items}</ol>
  <img class="crop" src="layout/{e(r['name'])}.png" alt=""></section>""")
        none = "" if changed or lay else "<p class='none'>変化なし: 撮った画面はすべて基準画像と同じでした。崩れも見つかっていません。</p>"
        toc = "".join(f"<li><a href='#s_{e(r['name'])}'>{e(r['title'])}</a> — {e(r['sub'])}</li>" for r in changed)
        return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>画面の変化の確認</title>
<style>
body{{background:#15161a;color:#dde;font:14px/1.6 "Yu Gothic UI","Meiryo",sans-serif;margin:0;padding:16px 24px}}
h1{{font-size:20px}} h2{{font-size:17px;margin:0 0 4px;color:#ffd24a}} h2 small{{color:#889;font-weight:normal}} h3{{font-size:14px;margin:14px 0 6px}}
.how{{background:#1f2430;border:1px solid #344;border-radius:8px;padding:10px 16px}} code{{background:#000;padding:1px 6px;border-radius:4px;color:#9fe}}
.scr{{border-top:1px solid #333;padding:16px 0}} .sub{{color:#bbb;margin:0}} .regs{{color:#9ad;margin:4px 0}}
img.crop{{max-width:100%;border:1px solid #333}}
.viewer{{position:relative;display:inline-block;border:1px solid #444;max-width:100%}} .viewer img.v{{display:none;max-width:100%}} .viewer img.v.show{{display:block}}
.btns button{{background:#2a2f3a;color:#dde;border:1px solid #445;border-radius:5px;padding:2px 10px;margin-left:4px;cursor:pointer}} .btns button.on{{background:#4a6;color:#fff}}
.wipebox{{position:relative;display:inline-block;max-width:100%;border:1px solid #444}} .wipebox img{{display:block;max-width:100%}}
.wipeTop{{position:absolute;inset:0;overflow:hidden;width:50%;border-right:2px solid #ff2050}} .wipeTop img{{max-width:none}}
.none{{font-size:16px;color:#8f8}}
</style></head><body>
<h1>画面の変化の確認（tests/visual）</h1>
<div class="how">
<p>前回の基準画像と比べて<b>見た目が変わった画面だけ</b>を載せています（変化なしの画面は載せていません）。</p>
<p><b>意図した変化なら</b>（新しいボタンを足した等）、基準画像を今の画面で更新します:<br>
<code>.venv-build/Scripts/python.exe tools/run_tests.py visual --accept</code>（1画面だけなら <code>-k 画面の題名の一部</code> を付ける）</p>
<p><b>意図しない変化なら</b>、アプリを直してからもう一度 <code>tools/run_tests.py visual</code> を実行します。</p>
<p>判定: 色の差が {PIX_THR}/255 を超えた画素を「変化」とし、{MIN_PX}px 以上で「画面が変化した」とみなします。3Dビュー等の揺れる所は比較から除いています（差分の斜線）。</p>
</div>
{none}
{'<h2 style="margin-top:18px">変化した画面</h2><ul>' + toc + '</ul>' if changed else ''}
{''.join(secs)}
{'<h1>崩れの検出で見つかったもの</h1><p>重なり・はみ出し・文字の切れ等。画像の番号は一覧の番号です。意図した配置なら tests/visual/layout_allow.json に理由付きで足します。</p>' + ''.join(lsecs) if lsecs else ''}
<script>
for(const s of document.querySelectorAll('.scr')){{
  const v=s.querySelector('.viewer'); if(!v) continue;
  const show=k=>{{v.querySelectorAll('img.v').forEach(i=>i.classList.toggle('show',i.classList.contains(k)));
    s.querySelectorAll('.btns button').forEach(b=>b.classList.toggle('on',b.dataset.v===k));}};
  let timer=null; show('after');
  s.querySelectorAll('.btns button').forEach(b=>b.onclick=()=>{{ clearInterval(timer); timer=null;
    if(b.dataset.v==='flip'){{ let k='before'; show(k); b.classList.add('on'); timer=setInterval(()=>{{k=k==='before'?'after':'before'; show(k); b.classList.add('on');}},800); }}
    else show(b.dataset.v); }});
  const w=s.querySelector('.wipe'), top=s.querySelector('.wipeTop'), box=s.querySelector('.wipebox');
  const fit=()=>{{ top.querySelector('img').style.width=box.clientWidth+'px'; top.style.width=w.value+'%'; }};
  w.oninput=fit; addEventListener('resize',fit); box.querySelector('img').onload=fit; fit();
}}
</script></body></html>
"""


def _url(path):
    return "/" + Path(path).resolve().relative_to(ROOT).as_posix()


_RUNNERS = {}


def runner(t):
    r = _RUNNERS.get(id(t))
    if r is None:
        r = _RUNNERS[id(t)] = Runner(t)
    return r
