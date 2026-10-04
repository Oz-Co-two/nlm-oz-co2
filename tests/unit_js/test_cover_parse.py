"""js/media/cover-parse.js: 音源に埋め込まれたアートワークの抽出（純バイト解析）。
各形式（MP3/ID3, FLAC, OGG, MP4）の最小のバイト列をPython側で組み立てて、画像データとMIMEが取れるか確認する。"""
import base64
import struct

PNG = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) + b"PNGDATA"
JPG = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"JPGDATA"

HEAD = "const m = await import('/js/media/cover-parse.js');\nconst U = a => Uint8Array.from(a);\n"


def _js(t, body):
    return t.ed.js("(async () => {" + HEAD + body + "})()")


def synchsafe(n):
    return bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])


def id3v23(img, mime=b"image/png", frame=b"APIC", enc=0, ver=3):
    body = bytes([enc]) + mime + b"\0" + bytes([3]) + (b"\0" if enc == 0 else b"\0\0") + img
    size = struct.pack(">I", len(body)) if ver == 3 else synchsafe(len(body))
    frames = frame + size + b"\0\0" + body
    return b"ID3" + bytes([ver, 0, 0]) + synchsafe(len(frames)) + frames


def id3v22(img):
    body = bytes([0]) + b"PNG" + bytes([3]) + b"\0" + img
    frames = b"PIC" + bytes([0, (len(body) >> 8) & 255, len(body) & 255]) + body
    return b"ID3" + bytes([2, 0, 0]) + synchsafe(len(frames)) + frames


def flac_pic_body(img, mime=b"image/png"):
    return (struct.pack(">I", 3) + struct.pack(">I", len(mime)) + mime + struct.pack(">I", 0) + b"\0" * 16
            + struct.pack(">I", len(img)) + img)


def flac_blocks(img):
    """"fLaC" の後ろ: STREAMINFO風のダミー(type0・最後ではない)→PICTURE(type6・最後)"""
    dummy = b"\0" * 34
    pic = flac_pic_body(img)
    return (bytes([0x00]) + len(dummy).to_bytes(3, "big") + dummy + bytes([0x86]) + len(pic).to_bytes(3, "big") + pic)


def ogg(img, opus=False):
    pic = base64.b64encode(flac_pic_body(img))
    head = b"OpusHead" + b"\0" * 11 if opus else b"\x01vorbis" + b"\0" * 23
    vendor = b"v"
    comment = (b"OpusTags" if opus else b"\x03vorbis") + struct.pack("<I", len(vendor)) + vendor + struct.pack("<I", 1)
    c = b"METADATA_BLOCK_PICTURE=" + pic
    comment += struct.pack("<I", len(c)) + c
    if not opus:
        comment += b"\x01"
    lace = b""
    for pk in (head, comment):
        n = len(pk)
        lace += bytes([255]) * (n // 255) + bytes([n % 255])
    return b"OggS" + bytes([0, 2]) + b"\0" * 20 + bytes([len(lace)]) + lace + head + comment


def atom(typ, payload):
    return struct.pack(">I", len(payload) + 8) + typ + payload


def mp4(img):
    data = atom(b"data", b"\0\0\0\x0e\0\0\0\0" + img)
    covr = atom(b"covr", data)
    ilst = atom(b"ilst", covr)
    meta = atom(b"meta", b"\0\0\0\0" + ilst)
    udta = atom(b"udta", meta)
    return atom(b"ftyp", b"M4A \0\0\0\0") + atom(b"moov", udta)


def run(t, name, raw):
    """raw を関数 name に渡して {mime, data(リスト)} か null を返す"""
    return _js(t, f"const r = m.{name}(U({list(raw)})); return r && {{ mime: r.mime, data: Array.from(r.data) }};")


def test_sniff_mime(t):
    '''_sniffMime: 先頭バイトでpng/jpeg/gif/bmpを判別し、不明はjpeg'''
    t.fresh()
    r = _js(t, """return [[0x89, 0x50], [0xFF, 0xD8], [0x47, 0x49, 0x46], [0x42, 0x4D], [0, 0, 0]].map(a => m._sniffMime(U(a)));""")
    t.eq(r, ['image/png', 'image/jpeg', 'image/gif', 'image/bmp', 'image/jpeg'], 'MIME')
    t.eq(_js(t, "return m._rd32be(U([0xFF, 0, 0, 1]), 0);"), 0xFF000001, '_rd32be は符号なし')
    t.no_errors()


def test_id3(t):
    '''MP3(ID3v2.2/2.3/2.4): APIC/PIC フレームの画像とMIMEが取れる。画像の無いタグはnull'''
    r = run(t, "_id3Pic", id3v23(PNG))
    t.eq((r['mime'], bytes(r['data'])), ('image/png', PNG), 'ID3v2.3 PNG')
    r = run(t, "_id3Pic", id3v23(JPG, b"image/jpeg"))
    t.eq((r['mime'], bytes(r['data'])), ('image/jpeg', JPG), 'ID3v2.3 JPEG')
    r = run(t, "_id3Pic", id3v23(PNG, ver=4))
    t.eq(bytes(r['data']), PNG, 'ID3v2.4（フレームサイズがsynchsafe）')
    r = run(t, "_id3Pic", id3v23(PNG, enc=1))
    t.eq(bytes(r['data']), PNG, 'UTF-16の説明文')
    r = run(t, "_id3Pic", id3v22(PNG))
    t.eq((r['mime'], bytes(r['data'])), ('image/png', PNG), 'ID3v2.2 PIC')
    t.eq(run(t, "_id3Pic", id3v23(PNG, frame=b"TIT2")), None, 'APICが無ければnull')
    t.no_errors()


def test_flac(t):
    '''FLAC: PICTUREブロック(type6)の画像とMIMEが取れる。ブロックが無ければnull'''
    r = run(t, "_flacPic", flac_blocks(PNG))
    t.eq((r['mime'], bytes(r['data'])), ('image/png', PNG), 'FLAC')
    only_dummy = bytes([0x80]) + (34).to_bytes(3, "big") + b"\0" * 34
    t.eq(run(t, "_flacPic", only_dummy), None, 'PICTUREが無ければnull')
    t.no_errors()


def test_ogg(t):
    '''OGG(Vorbis)/Opus: コメントの METADATA_BLOCK_PICTURE(base64) から画像が取れる。コメントに無ければnull'''
    r = run(t, "_oggPic", ogg(JPG))
    t.ok(r, 'Vorbis')
    t.eq(bytes(r['data']), JPG, 'Vorbisの画像')
    r = run(t, "_oggPic", ogg(PNG, opus=True))
    t.ok(r, 'Opus')
    t.eq((r['mime'], bytes(r['data'])), ('image/png', PNG), 'Opusの画像')
    t.eq(run(t, "_oggPic", b"not an ogg stream at all............."), None, 'OggSで始まらなければnull')
    t.no_errors()


def test_mp4(t):
    '''MP4/M4A: moov>udta>meta>ilst>covr>data の画像が取れる。covr が無ければnull'''
    r = run(t, "_mp4Pic", mp4(JPG))
    t.eq((r['mime'], bytes(r['data'])), ('image/jpeg', JPG), 'MP4')
    r = run(t, "_mp4Pic", mp4(PNG))
    t.eq((r['mime'], bytes(r['data'])), ('image/png', PNG), 'MP4 PNG')
    t.eq(run(t, "_mp4Pic", atom(b"ftyp", b"M4A \0\0\0\0") + atom(b"moov", atom(b"free", b"xx"))), None, 'covrが無ければnull')
    t.no_errors()


def test_truncated_input_safe(t):
    '''壊れた/途中で切れた入力でも例外にならずnull（他人のファイルを読むため）'''
    for name, raw in (("_id3Pic", id3v23(PNG)[:14]), ("_flacPic", flac_blocks(PNG)[:40]), ("_oggPic", ogg(PNG)[:30]),
                      ("_mp4Pic", mp4(PNG)[:20]), ("_id3Pic", b"ID3\x03\0\0\0\0\0\0")):
        try:
            r = run(t, name, raw)
        except Exception as e:
            raise AssertionError(f"{name}: 切れた入力で例外 {e}")
        t.ok(r is None or r.get("data") is not None, f"{name}: nullか結果")
    t.no_errors()
