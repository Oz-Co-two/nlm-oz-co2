"""曲の解析（テンポの推定・構成の解析）。本体に同梱し、serve.py の /__analysis/* から使う（2026-10-19）。

- tempo.py     … BPM・無音追加の提案（tools/tempo_leadin.py の中身）
- structure.py … 区切り・同じ/似ている区間・セクション・名前の推測（tools/analyze_structure.py の中身）
- service.py   … 音源の一時保存と、解析を1件ずつ別スレッドで回す仕事の列（serve.py が使う）
- hpss()       … 調波・打楽器成分を1回で分ける（テンポの推定と構成の解析で使い回す）

Auto Note Plotter（別のリポジトリ nlm-automap）がこのフォルダの4つのファイルを手を加えずに写して使っている。関数の名前・引数・
戻り値の形を変える時と、ファイルを足す時はその写し方（nlm-automap の tools/sync_nlm_analysis.py）も考えること。

librosa・numpy・scipy・scikit-learn は解析を始めた時に読み込む（serve.py の起動を遅くしないため。この __init__ と
service.py は標準ライブラリだけで読み込める）。
"""
import sys
import types

RESULT_VERSION = 1   # 解析結果の形の版（JS がプロジェクトに保存する。形を変えたら上げる）


def hpss(y):
    """音 y を (調波成分, 打楽器成分) に分ける＝librosa.effects.hpss(y)。librosa.effects.harmonic(y)・percussive(y) と
    1ビットも同じ値（3つとも同じ STFT・同じ中央値フィルタ2つ・同じマスク・同じ逆変換で、harmonic・percussive は
    両方の成分を計算してから片方を捨てている。librosa 1.0 のソースで確かめた・2026-11-11）。
    テンポの推定（tempo.onset_env の yp）と構成の解析（structure.measure_at の yh）へ渡すと、HPSS が1回で済む"""
    import librosa
    return librosa.effects.hpss(y)


def _hpss_part(y, given, split):
    """HPSS の片方: 渡された物（hpss(y) の片方。形が y と違えば取り違え）か、無ければ split(y)（harmonic・percussive）"""
    if given is None:
        return split(y)
    if getattr(given, "shape", None) != y.shape or getattr(given, "dtype", None) != y.dtype:
        raise ValueError("HPSS の成分の形・型が音と違う")
    return given


def expose(core, module_name):
    """tools/ のコマンド（tempo_leadin.py・analyze_structure.py）用: core の名前を全部そのモジュールに見せ、
    そのモジュールへの代入（例: 調整用のスクリプトの A.SECTION_SAME = 0.5）を core にも反映する。
    中身を song_analysis へ移した後も、tools のモジュールの定数を書き換えて試すスクリプトがそのまま効くように。"""
    mod = sys.modules[module_name]
    for k, v in vars(core).items():
        if not k.startswith("__") and k not in mod.__dict__:
            mod.__dict__[k] = v

    class _Linked(types.ModuleType):
        def __setattr__(self, k, v):
            if k in vars(core):
                setattr(core, k, v)
            super().__setattr__(k, v)

    mod.__class__ = _Linked
