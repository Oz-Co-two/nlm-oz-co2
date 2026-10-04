def test_boot(t):
    '''起動してテスト素材を読める（土台の確認）'''
    ed = t.fresh('basic')
    t.eq(ed.js("window._dbgApp.state().counts.notes"), 8, 'basic のノーツ数')
    t.no_errors()


def test_reload_resets(t):
    '''開き直すと空の状態に戻る'''
    ed = t.fresh()
    t.eq(ed.js("window._dbgApp.state().counts.notes"), 0, '開き直し後のノーツ数')
    t.no_errors()
