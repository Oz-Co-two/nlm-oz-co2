"""BL評価リスト（js/mapcheck/blcriteria.js）と譜面チェック（mapcheck.js）を、本物の譜面フォルダにかけて結果を集める。
ランクになった譜面（審査を通った版）で「違反」が出たら、まず判定の誤り（誤検出）を疑える＝判定の正確さを数字で見るための台本。

利用者が NLM で譜面をチェックする時と同じ道を通す（変換を別に書かない）:
  MEDIA の記録したライブラリ（config/library.json）→ 右クリック「曲データを読み込む」（bulkLoadSongData）→
  INFO で読み込んだ曲情報・カバー画像のノードを書き出しへ繋ぐ（利用者が手で繋ぐ所）→ collectMapCheckInput → runMapCheck → runBlCriteria
R5.A（視界ブロック）の★/Tech は一覧の値を渡す（画面の欄に手で入れたのと同じ）。同じ検出で AutoModder の式
（(750-300)·e^(-Pass/7.6 - Tech·0.06) + 325 ms）でも数える: 公式の式 (750-325)·e^(-x/7.6 - Tech·0.06) + 325 に
x = Pass - 7.6·ln(450/425) を入れると AutoModder の式と同じ値になる＝判定のコードを変えずに測れる。

譜面フォルダは読むだけ（ライブラリの走査・ファイルの読み出しは media_library.py＝読むだけの経路）。キャッシュ等はすべて一時フォルダ。
ネットへは出ない（NLM_NO_NET=1）。

使い方（.venv-build の Python で）:
  python tools/bl_ranked_check.py --list <一覧.json> --out <出力フォルダ> [--workers 4] [--only key1,key2] [--limit N]
一覧の形: {"maps":[{"hash","key","song","mapper","period","folder","ranked_diffs":[{"mode","difficulty","stars","tech","pass",…}]}]}
出力: <出力フォルダ>/nlm_results.jsonl（1行に1難易度）・nlm_results_maps.jsonl（1行に1譜面の生の結果）・run_log.txt
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass

AM_SHIFT = 7.6 * math.log(450 / 425)   # AutoModder の式を公式の式の形で表した時の★のずれ

# 1譜面の処理（ページの中）。ROOT/REL/STARS/STARS_AM を置き換えて使う
JOB_JS = r"""(async()=>{
  const out={t0:performance.now()};
  window.__job=null;
  try{
    const rt=window._dbg.rt, A=window._dbgApp;
    const norm=s=>String(s||'').replace(/[\\\/]+$/,'').toLowerCase();
    const lib=rt.libDirs.find(l=>l.native&&norm(l.path)===norm(__ROOT__));
    if(!lib){ out.error='lib-not-found'; return out; }
    const item=lib.items.find(it=>it.entry&&it.rel===__REL__);
    if(!item){ out.error='item-not-found'; return out; }
    out.v4=!!item._v4;
    const before=new Set(Object.keys(rt.infoGraph.nodes));
    const toastEl=document.getElementById('errToast'); if(toastEl) toastEl.textContent='';
    await rt.bulkLoadSongData(item);   // MEDIA の右クリック「曲データを読み込む」と同じ
    out.toast=(document.getElementById('errToast')||{}).textContent||'';
    out.srcEnv=(item.info&&item.info._environmentName)||null;
    // 読み込んだ曲情報・カバー画像のノードは未接続で作られる（利用者が書き出しへ繋ぐ）。画面のドラッグでの接続と同じ処理
    const ig=rt.infoGraph, live=A.infoGraph();
    out.igLive=JSON.stringify(Object.keys(ig.nodes).sort())===JSON.stringify(Object.keys(live.nodes).sort());
    const wired=[];
    for(const k of Object.keys(ig.nodes)){ if(before.has(k)) continue; const t=ig.nodes[k].t; if(t!=='meta'&&t!=='cover') continue;
      ig.edges=(ig.edges||[]).filter(e=>!(e.o===ig.activeOut&&rt.infoNodeT(e.s)===t)); ig.edges.push({s:k,o:ig.activeOut}); wired.push(t); }
    rt.applyInfoGraph();
    out.wired=wired;
    const inp=await A.mapCheckInput();
    if(!inp||inp.error){ out.error='input: '+(inp&&inp.error); return out; }
    const MC=await import('/js/mapcheck/mapcheck.js'), BLm=await import('/js/mapcheck/blcriteria.js');
    const mc=MC.runMapCheck(inp);
    const bl=BLm.runBlCriteria({...inp,stars:__STARS__},mc);
    const blAM=BLm.runBlCriteria({...inp,stars:__STARS_AM__},mc);
    const ob=o=>[o.beat,o.kind,o.x,o.y,o.c];
    const rules=res=>res.rules.map(r=>({id:r.id,kind:r.kind,status:r.status,f:r.findings.map(f=>({d:f.d,s:f.status,k:f.key,v:f.vars,o:f.objs?f.objs.map(ob):null}))}));
    out.bl=rules(bl);
    out.r5am=rules(blAM).find(r=>r.id==='R5.A');
    out.mc={general:mc.general.map(g=>({k:g.key,s:g.status,l:g.label,v:g.vars})),
      diffs:mc.diffs.map(d=>({d:d.difficulty,e:d.error||null,r:d.results.map(r=>({k:r.key,s:r.status,l:r.label,v:r.vars,o:r.objs?r.objs.map(o=>o.beat):null}))}))};
    out.input={bpm:inp.info.bpm,env:inp.info.environment,prev:[inp.info.previewStart,inp.info.previewDuration],meta:inp.meta,infoRaw:inp.infoRaw,
      cover:inp.cover,audio:inp.audioDuration,
      diffs:inp.diffs.map(d=>({d:d.difficulty,njs:d.njs,off:d.njsOffset,ver:d.json.version,notes:(d.json.colorNotes||[]).length,
        bombs:(d.json.bombNotes||[]).length,walls:(d.json.obstacles||[]).length,arcs:(d.json.sliders||[]).length,chains:(d.json.burstSliders||[]).length,
        lights:(d.json.basicBeatmapEvents||[]).length,bpmEvents:(d.json.bpmEvents||[]).length}))};
  }catch(e){ out.error='exception: '+String(e&&e.stack||e); }
  finally{ out.ms=Math.round(performance.now()-out.t0); delete out.t0; window.__job=out; }
  return true;
})()"""


def js_str(s):
    return json.dumps(s, ensure_ascii=False)


def stars_of(m, am=False):
    """{難易度: {star, tech}}（Standard のランクの難易度だけ。am=True は AutoModder の式になる★）"""
    out = {}
    for r in m["ranked_diffs"]:
        if r["mode"] != "Standard":
            continue
        if am:
            s = r["pass"] - AM_SHIFT
            if s < 0:
                continue   # 公式の式の形では表せない（ランクの譜面では起きない値）
            out[r["difficulty"]] = {"star": s, "tech": r["tech"]}
        else:
            out[r["difficulty"]] = {"star": r["stars"], "tech": r["tech"]}
    return out


def seed_scan(roots, seed_dir):
    """ライブラリを Python で1回走査して、キャッシュ（config/library_cache.json）を作る（読むだけ）。各作業の Edge はこれを写して使う"""
    sys.path.insert(0, str(ROOT))
    import media_library
    cfg = Path(seed_dir) / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "library.json").write_text(json.dumps({"libs": [{"path": r} for r in roots]}, ensure_ascii=False), encoding="utf-8")
    lib = media_library.MediaLibrary(seed_dir, default_playdata=str(Path(seed_dir) / "PlayerData.dat"))
    for l in lib.list():
        while True:
            r = lib.scan(l["id"])
            if r.get("done"):
                print(f"  走査: {l['path']} … {r['progress']['total']} 譜面（読めなかった {r.get('skipped', 0)}）", flush=True)
                break
            time.sleep(1)
    return cfg / "library_cache.json"


def worker(args):
    import cdp
    from cdp import Editor, CdpError
    # ライトのイベントが10万を超える譜面は、読み込みと判定でページが数分ふさがる＝その間は CDP の応答も返らない（既定の60秒では切れる）
    cdp._Pipe.TIMEOUT = 1800
    data = json.loads(Path(args.list).read_text(encoding="utf-8"))
    maps = [m for m in data["maps"] if m["key"] in set(args.keys.split(","))]
    out_path = Path(args.part)
    roots = sorted({str(Path(m["folder"]).parent) for m in data["maps"]})
    with Editor(ready=True, max_fps=10) as ed, out_path.open("w", encoding="utf-8") as fo:
        cfg = Path(ed.data_dir) / "config"
        (cfg / "library.json").write_text(json.dumps({"libs": [{"path": r} for r in roots]}, ensure_ascii=False), encoding="utf-8")
        shutil.copy(args.seed_cache, cfg / "library_cache.json")
        for i, m in enumerate(maps):
            t0 = time.time()
            res = None
            for attempt in range(2):
                try:
                    ed.reload(clear_storage=False)   # 毎回まっさらなエディタから（起動時に記録したライブラリを読む）
                    end = time.time() + 300
                    while time.time() < end:
                        ok = ed.js("(()=>{const L=window._dbg.rt.libDirs.filter(l=>l.native);"
                                   f"return L.length==={len(roots)}&&L.every(l=>l.state!=='ok'||(!l.scanning&&l.items.length>0));}})()")
                        if ok:
                            break
                        time.sleep(0.3)
                    js = (JOB_JS.replace("__ROOT__", js_str(str(Path(m["folder"]).parent)))
                          .replace("__REL__", js_str(Path(m["folder"]).name))
                          .replace("__STARS_AM__", json.dumps(stars_of(m, am=True)))
                          .replace("__STARS__", json.dumps(stars_of(m))))
                    ed.js(js, await_promise=False)
                    end = time.time() + 1800
                    while time.time() < end:
                        res = ed.js("window.__job")
                        if res:
                            break
                        time.sleep(0.25)
                    if res is None:
                        res = {"error": "timeout"}
                    break
                except (CdpError, TimeoutError) as e:
                    res = {"error": f"cdp: {e}"}
            res["pageErrors"] = ed.errors()[:10]
            ed._events.clear()
            res.update({"hash": m["hash"], "key": m["key"], "wall": round(time.time() - t0, 1)})
            fo.write(json.dumps(res, ensure_ascii=False) + "\n")
            fo.flush()
            print(f"[{args.wid}] {i + 1}/{len(maps)} {m['key']} {res.get('error') or 'ok'} {res['wall']}s", flush=True)


def per_diff_rows(m, res):
    """1譜面の結果 → ランクの難易度ごとの行"""
    rows = []
    exported = {d["d"] for d in (res.get("input") or {}).get("diffs", [])}
    for r in m["ranked_diffs"]:
        dn = r["difficulty"]
        row = {"hash": m["hash"], "key": m["key"], "song": m["song"], "mapper": m["mapper"], "mode": r["mode"], "difficulty": dn,
               "period": m["period"], "stars": r["stars"], "tech": r["tech"], "pass": r["pass"]}
        if r["mode"] != "Standard":
            row["skipped"] = "mode"   # NLM の「曲データを読み込む」は Standard だけ
            rows.append(row)
            continue
        if res.get("error"):
            row["error"] = res["error"]
            if res.get("toast"):
                row["toast"] = res["toast"]
            rows.append(row)
            continue
        if dn not in exported:
            row["error"] = "not-exported"   # 読み込んだが書き出しの対象にならなかった
            rows.append(row)
            continue
        bl = []
        for rule in res["bl"]:
            fs = [f for f in rule["f"] if f["d"] in (None, dn)]
            st = "fail" if any(f["s"] == "fail" for f in fs) else "check" if any(f["s"] == "check" for f in fs) else None
            if not st:
                continue
            bl.append({"id": rule["id"], "status": st, "findings": [
                {"key": f["k"], "status": f["s"], "scope": "map" if f["d"] is None else "diff", "vars": f["v"],
                 "beats": [o[0] for o in f["o"]] if f["o"] else None}
                for f in fs if f["s"] in ("fail", "check")]})
        row["bl"] = bl
        mcd = next((d for d in res["mc"]["diffs"] if d["d"] == dn), None)
        row["mc"] = {"general": res["mc"]["general"],
                     "error": mcd and mcd["e"],
                     "results": [{"key": x["k"], "status": x["s"], "label": x["l"], "beats": x["o"]} for x in (mcd["r"] if mcd else [])]}
        # R5.A: 公式の式で出た物と、AutoModder の式で出た物の差
        def r5(rule):
            s = set()
            for f in rule["f"]:
                if f["d"] == dn and f["k"] == "vision" and f["o"]:
                    s.update(tuple(o) for o in f["o"])
            return s
        off = r5(next(x for x in res["bl"] if x["id"] == "R5.A"))
        am = r5(res["r5am"]) if res.get("r5am") else set()
        row["r5a"] = {"official": len(off), "automodder": len(am), "amOnly": sorted([list(o) for o in am - off])[:200],
                      "amOnlyN": len(am - off), "officialOnlyN": len(off - am),
                      "officialMs": round((750 - 325) * math.exp(-r["stars"] / 7.6 - r["tech"] * 0.06) + 325, 1),
                      "amMs": round((750 - 300) * math.exp(-r["pass"] / 7.6 - r["tech"] * 0.06) + 325, 1)}
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser(description="BL評価リスト・譜面チェックを本物の譜面フォルダにかけて結果を集める")
    ap.add_argument("--list", required=True, help="譜面の一覧（JSON）")
    ap.add_argument("--out", required=True, help="結果を書くフォルダ")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", help="key をカンマ区切り")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--keep", action="store_true", help="出力フォルダの前の結果を残し、今回流した譜面だけ置き換える（流れなかった譜面の流し直し用）")
    ap.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--keys", help=argparse.SUPPRESS)
    ap.add_argument("--part", help=argparse.SUPPRESS)
    ap.add_argument("--seed-cache", help=argparse.SUPPRESS)
    ap.add_argument("--wid", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.worker:
        worker(args)
        return
    data = json.loads(Path(args.list).read_text(encoding="utf-8"))
    maps = data["maps"]
    if args.only:
        maps = [m for m in maps if m["key"] in set(args.only.split(","))]
    if args.limit:
        maps = maps[:args.limit]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    seed = tempfile.mkdtemp(prefix="nlm_blrank_seed_")
    roots = sorted({str(Path(m["folder"]).parent) for m in data["maps"]})
    print("ライブラリの走査（キャッシュ作り）…", flush=True)
    cache = seed_scan(roots, seed)
    t_scan = time.time() - t0
    n = max(1, min(args.workers, len(maps)))
    # 重い譜面が偏らないよう、ランクの難易度の数で交互に配る
    shards = [[] for _ in range(n)]
    for i, m in enumerate(sorted(maps, key=lambda m: -len(m["ranked_diffs"]))):
        shards[i % n].append(m["key"])
    procs, parts = [], []
    for i, keys in enumerate(shards):
        part = out / f".part{i}.jsonl"
        parts.append(part)
        procs.append(subprocess.Popen([sys.executable, __file__, "--worker", "--list", args.list, "--out", str(out), "--keys", ",".join(keys),
                                       "--part", str(part), "--seed-cache", str(cache), "--wid", str(i)]))
    for p in procs:
        p.wait()
    by_key = {}
    for part in parts:
        if part.exists():
            for line in part.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    by_key[r["key"]] = r
            part.unlink()
    keep = {}
    if args.keep and (out / "nlm_results_maps.jsonl").exists():
        for line in (out / "nlm_results_maps.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(line) if line.strip() else {}
            if r.get("key") and r.get("error") != "not-run":
                keep[r["key"]] = r
    with (out / "nlm_results_maps.jsonl").open("w", encoding="utf-8") as fm, (out / "nlm_results.jsonl").open("w", encoding="utf-8") as fd:
        for m in (data["maps"] if args.keep else maps):
            res = by_key.get(m["key"]) or keep.get(m["key"]) or {"error": "not-run", "key": m["key"]}
            fm.write(json.dumps(res, ensure_ascii=False) + "\n")
            for row in per_diff_rows(m, res):
                fd.write(json.dumps(row, ensure_ascii=False) + "\n")
    total = time.time() - t0
    log = f"譜面 {len(maps)}・作業 {n}・走査 {t_scan:.0f} 秒・全体 {total:.0f} 秒\n"
    with (out / "run_log.txt").open("a" if args.keep else "w", encoding="utf-8") as f:
        f.write(("流し直し: " if args.keep else "") + log)
    shutil.rmtree(seed, ignore_errors=True)
    print(log, end="")


if __name__ == "__main__":
    main()
