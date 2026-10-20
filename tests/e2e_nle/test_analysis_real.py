"""曲の解析: 画面（js/analysis/song-analysis.js）と本物の解析（serve.py の /__analysis/*・song_analysis）をつないだ確かめ。
偽の応答は使わない（test_analysis.py は画面側だけを偽の応答で細かく見る）。素材 basic は BPM 120・音源16秒のクリック。
1回目の解析は解析の部品の読み込みに数秒かかるので、待ち時間を長めにしている。"""
from analysis_helpers import ana, dialog_choose, start_from_menu
from e2e_helpers import wait_until
from nle_helpers import open_nle


def test_analysis_real_backend(t):
    '''「曲を解析」を本物の解析で最後まで: 音源を送る→テンポ（今の設定と違えば確認の画面→「適用しない」）→構成→帯が出る。
    エラーの知らせが出ない・帯に1つ以上のセクションがあり名前が付く・結果がプロジェクトのデータに入る'''
    ed = open_nle(t, "basic")
    wait_until(ed, "!document.getElementById('bootCover')&&window._dbgApp.analysis().startBtn", label="［曲を解析］が出る")
    ed.js("(e=>{e.style.display='none'; e.textContent=''; return 1})(document.getElementById('errToast'))")   # 音源を配置した知らせ（✅）を消す
    start_from_menu(ed)
    state = wait_until(ed, """(()=>{ if(document.querySelector('#dirtyDlg.anaTempo')) return 'dialog';
        const a=window._dbgApp.analysis(); if(a&&a.shown&&!a.running&&a.labels.length) return 'band';
        const e=document.getElementById('errToast'); if(e&&e.style.display!=='none'&&e.textContent&&!e.textContent.startsWith('✅')) return 'err:'+e.textContent;
        return null; })()""", timeout=180, label="テンポの確認の画面か帯")
    if state == "dialog":
        dialog_choose(ed, "none")
        state = wait_until(ed, """(()=>{ const a=window._dbgApp.analysis(); if(a&&a.shown&&!a.running&&a.labels.length) return 'band';
            const e=document.getElementById('errToast'); if(e&&e.style.display!=='none'&&e.textContent&&!e.textContent.startsWith('✅')) return 'err:'+e.textContent;
            return null; })()""", timeout=180, label="帯")
    t.eq(state, "band", "本物の解析で帯が出る（エラーにならない）")
    a = ana(ed)
    t.ok(len(a["labels"]) >= 1 and all(isinstance(s, str) and s for s in a["labels"]), f"帯のセクションに名前と番号: {a['labels']}")
    t.ok(len(a["groups"]) >= 1, f"細かい区切り: {a['groups']}")
    d = a["data"]
    t.ok(d["tempo"] and isinstance(d["tempo"].get("bpm"), (int, float)), "テンポの結果を持つ")
    t.ok(d["structure"] and len(d["structure"]["sections"]) == len(a["labels"]), "構成の結果を持つ")
