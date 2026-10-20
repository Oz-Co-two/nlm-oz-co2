"""曲の解析（テンポの推定・構成の解析）。本体に同梱し、serve.py の /__analysis/* から使う（2026-10-19）。

- tempo.py     … BPM・無音追加の提案（tools/tempo_leadin.py の中身）
- structure.py … 区切り・同じ/似ている区間・セクション・名前の推測（tools/analyze_structure.py の中身）
- service.py   … 音源の一時保存と、解析を1件ずつ別スレッドで回す仕事の列（serve.py が使う）

librosa・numpy・scipy・scikit-learn は解析を始めた時に読み込む（serve.py の起動を遅くしないため。この __init__ と
service.py は標準ライブラリだけで読み込める）。
"""
import sys
import types

RESULT_VERSION = 1   # 解析結果の形の版（JS がプロジェクトに保存する。形を変えたら上げる）


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
