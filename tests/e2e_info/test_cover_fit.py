"""カバー画像の補正の適用（カバーノードに画像 → 譜面チェックの「🖼 カバー画像を補正…」→ 確認画面 → 書き出し）。
画像は canvas で作り、ファイル選択（showOpenFilePicker）とフォルダ選択（showDirectoryPicker）だけをページ内で差し替える。"""
import json

from info_helpers import (click_sel, click_text, dialog_text, image_size, install_pickers, open_fixture, open_mapcheck,
                          pixel, set_pick_image, to_info, toast, type_text, undo, wait_dialog, wait_dialog_closed,
                          wait_mapcheck_done, wait_until, written, written_text)

PNG_HEAD = [137, 80, 78, 71]
JPG_HEAD = [255, 216, 255]
C1 = '#infoWorld .iGrp[data-node=c1]'


def _fit(ed):
    return ed.js("window._dbgApp.coverFit()")


def _pick_cover(ed, w, h, mime='image/png', name='art.png', colors=("#e03030", "#3050e0")):
    """INFOのカバーノード(c1)の「画像を選択…」を本物のクリックで押し、選んだ画像が読めて表示されるまで待つ"""
    set_pick_image(ed, w, h, mime, name, colors)
    click_sel(ed, f'{C1} .nPick', 'カバーの「画像を選択」')
    wait_until(ed, f"window._dbgApp.infoGraph().nodes.c1.data.name==={json.dumps(name)}", label='カバーの名前')
    wait_until(ed, f"document.querySelector('{C1} .nThumb').style.display==='block'", label='カバーの見本')


def _start(t, w, h, mime='image/png', name='art.png', colors=("#e03030", "#3050e0")):
    ed = open_fixture(t, 'rich')
    to_info(ed)
    install_pickers(ed)
    _pick_cover(ed, w, h, mime, name, colors)
    return ed


def _open_dialog(ed):
    """譜面チェック → 「🖼 カバー画像を補正…」→ 確認画面"""
    _open_panel(ed)
    click_sel(ed, '#mcPanel .mcFix[data-fix=cover]', '🖼 カバー画像を補正…')
    return wait_dialog(ed)


def _open_panel(ed):
    """譜面チェックのパネルを開く（既に開いていれば「再チェック」を押して今の状態で調べ直す）"""
    if ed.js("(()=>{const p=document.getElementById('mcPanel');return !!p&&p.style.display!=='none'})()"):
        click_sel(ed, '#mcPanel .mcRerun', '再チェック')
        wait_mapcheck_done(ed)
    else:
        open_mapcheck(ed)


def _close_panel(ed):
    """譜面チェックのパネルを閉じる（INFOのノードに被って押せなくなるため）"""
    if ed.js("(()=>{const p=document.getElementById('mcPanel');return !!p&&p.style.display!=='none'})()"):
        click_sel(ed, '#mcPanel .mcClose', '譜面チェックを閉じる')
        wait_until(ed, "document.getElementById('mcPanel').style.display==='none'", label='パネルが閉じる')


def _apply(ed):
    click_text(ed, '#dirtyDlg button', '補正する')
    wait_dialog_closed(ed)


def _choose_mode(ed, mode):
    click_sel(ed, f'#dirtyDlg input[name=cfMode][value={mode}]', f'補正のしかた {mode}')


def _export(ed, folder='cvtest'):
    """偽の出力フォルダを選び、フォルダ名を入力し、INFOの「書き出し」ボタンで書き出す。書いたファイル名の一覧を返す"""
    _close_panel(ed)
    out = '#infoWorld .iGrp[data-out=o1]'
    click_sel(ed, f'{out} .oPick', '出力フォルダを選択')
    wait_until(ed, "window._dbgApp.infoGraph().outs.o1.outDirName==='CustomLevels'", label='出力フォルダ')
    click_sel(ed, f'{out} .oName', 'フォルダ名の入力欄')
    type_text(ed, folder)
    wait_until(ed, f"window._dbgApp.infoGraph().outs.o1.folderName==={json.dumps(folder)}", label='フォルダ名')
    click_sel(ed, '#iExport', '書き出しボタン')
    wait_until(ed, f"!!window.__fsw['CustomLevels/{folder}/Info.dat']", timeout=15, label='Info.dat の書き出し')
    ed.wait(0.3)
    return sorted(k.split('/')[-1] for k in written(ed))


def _info_dat(ed, folder='cvtest'):
    return json.loads(written_text(ed, f'CustomLevels/{folder}/Info.dat'))


def test_cover_fit_dialog_webp_crop(t):
    '''非正方形(300x200)・小さい・webp の画像: 確認画面に問題が出て、既定は「中央を切り抜く」。補正するとノードの設定とカードの表示に入る'''
    ed = _start(t, 300, 200, 'image/webp', 'art.webp')
    t.eq(_fit(ed), {'cid': 'c1', 'fit': None, 'card': ''}, '補正前は設定なし')
    txt = _open_dialog(ed)
    t.ok('art.webp（300×200）' in txt, f'今の画像: {txt}')
    for w in ('正方形でない', '256×256より小さい', '形式が png/jpg でない'):
        t.ok(w in txt, f'合わない所に「{w}」: {txt}')
    t.eq(ed.js("[...document.querySelectorAll('#dirtyDlg input[name=cfMode]')].map(r=>[r.value,r.checked])"),
         [['crop', True], ['stretch', False], ['pad', False]], '補正のしかた（既定は中央を切り抜く）')
    t.ok('補正後: art.png（256×256）' in txt, f'切り抜き後は短い辺200→256へ拡大: {txt}')
    _apply(ed)
    f = _fit(ed)
    t.eq(f['fit'], {'mode': 'crop', 'bg': '#000000'}, 'ノードの補正の設定')
    wait_until(ed, "window._dbgApp.coverFit().card!==''", label='カードの表示')
    t.eq(_fit(ed)['card'], '書き出し時に 300×200 → 256×256 へ補正（中央を切り抜き）', 'カードの表示')
    t.ok('カバー画像の補正を設定しました' in toast(ed), f'お知らせ: {toast(ed)}')
    # 補正の設定は保存内容に入り、元のファイル名・画像の参照は変わらない
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    t.eq(pj['infoGraph']['nodes']['c1']['data']['fit'], {'mode': 'crop', 'bg': '#000000'}, '保存内容に補正の設定')
    t.eq(pj['infoGraph']['nodes']['c1']['data']['name'], 'art.webp', '元のファイル名は変えない')
    # 譜面チェックをやり直すと、カバー画像の項目（と補正のボタン）が消える
    wait_mapcheck_done(ed)
    wait_until(ed, "document.querySelectorAll('#mcPanel .mcFix[data-fix=cover]').length===0", timeout=20, label='カバーの項目が消える')
    t.no_errors()


def test_cover_fit_export_crop(t):
    '''中央を切り抜く: 書き出した cover は 256x256 のpng。絵の中央が残る（左=赤・右=青の境目が中央）'''
    ed = _start(t, 300, 200, 'image/webp', 'art.webp')
    _open_dialog(ed)
    _apply(ed)
    names = _export(ed)
    t.ok('cover.png' in names and 'cover.webp' not in names, f'書き出したファイル: {names}')
    t.eq(_info_dat(ed)['_coverImageFilename'], 'cover.png', 'Info.dat のカバー名')
    sz = image_size(ed, 'CustomLevels/cvtest/cover.png')
    t.eq((sz['w'], sz['h'], sz['head']), (256, 256, PNG_HEAD), '補正後の寸法と形式')
    r, b = pixel(ed, 'CustomLevels/cvtest/cover.png', 20, 128), pixel(ed, 'CustomLevels/cvtest/cover.png', 235, 128)
    t.ok(r[0] > 180 and r[2] < 90, f'左は赤: {r}')
    t.ok(b[2] > 180 and b[0] < 90, f'右は青: {b}')
    t.no_errors()


def test_cover_fit_export_stretch(t):
    '''引き伸ばす: 長い辺(300)の正方形になり、全体が残る（左右の端が赤・青のまま）。確認画面の表示も更新される'''
    ed = _start(t, 300, 200, 'image/png', 'art.png')
    txt = _open_dialog(ed)
    t.ok('合わない所: 正方形でない / 256×256より小さい' in txt and '形式' not in txt.split('合わない所:')[1].split('\n')[0],
         f'png なので形式の問題は出ない: {txt}')
    _choose_mode(ed, 'stretch')
    wait_until(ed, "document.getElementById('dirtyDlg').innerText.includes('（300×300）')", label='確認画面の補正後の寸法')
    t.ok('縦横比が' in dialog_text(ed), '引き伸ばしの注意が出る')
    _apply(ed)
    t.eq(_fit(ed)['fit']['mode'], 'stretch', '設定')
    _export(ed)
    p = 'CustomLevels/cvtest/cover.png'
    sz = image_size(ed, p)
    t.eq((sz['w'], sz['h']), (300, 300), '補正後の寸法')
    t.ok(pixel(ed, p, 5, 150)[0] > 180 and pixel(ed, p, 295, 150)[2] > 180, '左端は赤・右端は青（全体が残る）')
    t.no_errors()


def test_cover_fit_export_pad(t):
    '''余白で埋める: 長い辺の正方形に、選んだ色の余白（上下）が付く。絵は歪まない'''
    ed = _start(t, 300, 200, 'image/png', 'art.png')
    _open_dialog(ed)
    _choose_mode(ed, 'pad')
    ed.js("""(()=>{const c=document.querySelector('#dirtyDlg input[type=color]'); c.value='#00ff00';
      c.dispatchEvent(new Event('input',{bubbles:true})); return c.value})()""")   # 色の選択ダイアログはOSのものなので値だけ入れる
    _apply(ed)
    t.eq(_fit(ed)['fit'], {'mode': 'pad', 'bg': '#00ff00'}, '設定')
    wait_until(ed, "window._dbgApp.coverFit().card!==''", label='カードの表示')
    t.ok('余白で埋める' in _fit(ed)['card'], f"カード: {_fit(ed)['card']}")
    _export(ed)
    p = 'CustomLevels/cvtest/cover.png'
    sz = image_size(ed, p)
    t.eq((sz['w'], sz['h']), (300, 300), '補正後の寸法')
    top, mid = pixel(ed, p, 150, 10), pixel(ed, p, 20, 150)
    t.ok(top[1] > 200 and top[0] < 60 and top[2] < 60, f'上の余白は緑: {top}')
    t.ok(mid[0] > 180, f'真ん中の左は絵（赤）: {mid}')
    t.no_errors()


def test_cover_fit_small_square_jpg(t):
    '''正方形だが小さい(128x128)jpg: 確認画面に補正のしかたは出ず、256x256のjpgになる（形式はjpgのまま）'''
    ed = _start(t, 128, 128, 'image/jpeg', 'small.jpg')
    txt = _open_dialog(ed)
    t.eq(ed.js("document.querySelectorAll('#dirtyDlg input[name=cfMode]').length"), 0, '正方形なので補正のしかたは選ばせない')
    t.ok('合わない所: 256×256より小さい' in txt, f'問題は大きさだけ: {txt}')
    _apply(ed)
    t.eq(_fit(ed)['fit']['mode'], 'crop', '設定')
    names = _export(ed)
    t.ok('cover.jpg' in names, f'書き出したファイル: {names}')
    sz = image_size(ed, 'CustomLevels/cvtest/cover.jpg')
    t.eq((sz['w'], sz['h'], sz['head'][:3]), (256, 256, JPG_HEAD), '拡大後の寸法とjpg形式')
    t.eq(_info_dat(ed)['_coverImageFilename'], 'cover.jpg', 'Info.dat のカバー名')
    t.no_errors()


def test_cover_fit_not_needed(t):
    '''基準を満たす画像(512x512 png)なら譜面チェックにカバーの項目も補正ボタンも出ない。書き出しは元の画像のまま'''
    ed = _start(t, 512, 512, 'image/png', 'good.png')
    _open_panel(ed)
    t.eq(ed.js("document.querySelectorAll('#mcPanel .mcFix[data-fix=cover]').length"), 0, '補正ボタン')
    _export(ed)
    p = 'CustomLevels/cvtest/cover.png'
    sz = image_size(ed, p)
    t.eq((sz['w'], sz['h']), (512, 512), '元のまま')
    t.eq(_fit(ed)['fit'], None, '設定なし')
    t.no_errors()


def test_cover_fit_cancel(t):
    '''確認画面でキャンセル・Esc なら設定は付かず、履歴も増えない'''
    ed = _start(t, 300, 200)
    _open_dialog(ed)
    u0 = ed.js("window._dbgApp.state().undo")   # 画面の選択の変化も1動作として履歴に入る＝パネルを開いた後の数から比べる
    click_text(ed, '#dirtyDlg button', 'キャンセル')
    wait_dialog_closed(ed)
    click_sel(ed, '#mcPanel .mcFix[data-fix=cover]', '補正ボタン')
    wait_dialog(ed)
    ed.key('Escape')
    wait_dialog_closed(ed)
    t.eq(_fit(ed)['fit'], None, '設定')
    t.eq(ed.js("window._dbgApp.state().undo"), u0, '履歴')
    t.no_errors()


def test_cover_fit_off_and_undo(t):
    '''カードの「補正をやめる」で設定が消え、書き出しは元の画像のまま。Undoで設定が戻り、さらにUndoで補正前に戻る'''
    ed = _start(t, 300, 200, 'image/webp', 'art.webp')
    _open_dialog(ed)
    _choose_mode(ed, 'stretch')
    _apply(ed)
    wait_until(ed, "window._dbgApp.coverFit().card!==''", label='カードの表示')
    click_sel(ed, f'{C1} .nCovFitOff', '補正をやめる')
    wait_until(ed, "window._dbgApp.coverFit().fit===null", label='設定が消える')
    t.eq(_fit(ed)['card'], '', 'カードの表示も消える')
    t.ok('補正をやめました' in toast(ed), f'お知らせ: {toast(ed)}')
    names = _export(ed)
    t.ok('cover.webp' in names and 'cover.png' not in names, f'補正なしの書き出し: {names}')
    sz = image_size(ed, 'CustomLevels/cvtest/cover.webp')
    t.eq((sz['w'], sz['h']), (300, 200), '元の寸法のまま')
    # Undo（書き出し先の選択やフォルダ名の入力も履歴に入っているので、補正の設定が戻るまで戻す）
    for _ in range(6):
        undo(ed)
        if _fit(ed)['fit']:
            break
    t.eq(_fit(ed)['fit'], {'mode': 'stretch', 'bg': '#000000'}, 'Undoで「補正をやめる」が取り消される')
    for _ in range(6):
        undo(ed)
        if not _fit(ed)['fit']:
            break
    t.eq(_fit(ed)['fit'], None, 'さらにUndoで補正前に戻る')
    t.no_errors()


def test_cover_fit_repick_clears(t):
    '''画像を選び直すと補正の設定は消える（前の画像向けの設定のため）。「再接続」で同じ名前の画像なら残り、別の名前なら消える'''
    ed = _start(t, 300, 200, 'image/png', 'art.png')
    _open_dialog(ed)
    _apply(ed)
    t.ok(_fit(ed)['fit'], '準備: 設定あり')
    # 「画像を選択」で同じ画像を選び直しても消える
    _pick_cover(ed, 300, 200, 'image/png', 'art.png')
    t.eq(_fit(ed)['fit'], None, '選び直したら設定が消える')
    # もう一度設定 → 再接続（出力フォルダ/カバー画像）
    ed.js("window._dbgApp.coverFit()")
    _open_dialog(ed)
    _apply(ed)
    t.ok(_fit(ed)['fit'], '準備: 再び設定あり')
    reco = '#infoWorld .iGrp[data-out=o1] .oReconnect'
    _close_panel(ed)
    wait_until(ed, f"(()=>{{const b=document.querySelector('{reco}');return !!b&&b.offsetWidth>0}})()", label='再接続ボタン')
    set_pick_image(ed, 300, 200, 'image/png', 'art.png')   # 同じ名前
    click_sel(ed, reco, '再接続')
    wait_until(ed, "window._dbgApp.infoGraph().outs.o1.outDirName==='CustomLevels'", label='出力フォルダの再接続')
    ed.wait(0.3)
    t.ok(_fit(ed)['fit'], '同じ名前の画像で再接続しても設定は残る')
    # 別の名前の画像で再接続 → 消える（ボタンはまだ出ている＝カバーは接続し直しが要る状態のまま）
    wait_until(ed, f"(()=>{{const b=document.querySelector('{reco}');return !!b&&b.offsetWidth>0}})()", label='再接続ボタン（2回目）')
    set_pick_image(ed, 300, 200, 'image/png', 'other.png')
    click_sel(ed, reco, '再接続')
    wait_until(ed, "window._dbgApp.infoGraph().nodes.c1.data.name==='other.png'", label='別の画像へ')
    t.eq(_fit(ed)['fit'], None, '別の名前の画像なら設定は消える')
    t.no_errors()
