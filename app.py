from __future__ import annotations

import hashlib
import json
import re
import shutil
import socket
import subprocess
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image

try:
    from config import SCREENSHOT_DIR
except ImportError as e:
    raise SystemExit(
        "config.py が見つかりません。config.example.py をコピーして作成してください。"
    ) from e

BASE_DIR = Path(__file__).resolve().parent
THUMB_DIR = BASE_DIR / "thumbnails"
CACHE_DIR = BASE_DIR / "cache"
VIEWED_FILE = BASE_DIR / "viewed.json"
SEEN_FILE = BASE_DIR / "seen.json"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
GIF_EXTS = {".gif"}
PDF_EXTS = {".pdf"}
VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".webm"}
# フォルダ(漫画ビューア)で縦に並べる対象
PAGE_EXTS = IMAGE_EXTS | GIF_EXTS
ALLOWED_EXTS = PAGE_EXTS | PDF_EXTS | VIDEO_EXTS

THUMB_SIZE = (300, 300)
# PDF ページのレンダリング目標幅(px)と拡大率の上限
PDF_PAGE_WIDTH = 1400
PDF_MAX_SCALE = 3.0
PORT = 8000

FFMPEG = shutil.which("ffmpeg")

THUMB_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

# トップレベルのファイル name -> {"mtime", "size", "type"}
IMAGES: dict[str, dict] = {}
# トップレベルのフォルダ name -> {"mtime", "files": [...], "sizes": [...] | None}
FOLDERS: dict[str, dict] = {}
VIEWED: dict[str, str] = {}
VIEWED_LOCK = threading.Lock()
SEEN: dict[str, str] = {}
NEW_ITEMS: set[str] = set()
# ループ回数の書き換えが不要だった GIF(毎回読み直さないための記録)
GIF_PASSTHROUGH: set[str] = set()

_NUM_RE = re.compile(r"(\d+)")


def natural_key(name: str) -> list:
    """1.png, 2.png, 10.png を数値順に並べるためのキー。"""
    return [int(t) if t.isdigit() else t.lower() for t in _NUM_RE.split(name)]


def file_type(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext in PDF_EXTS:
        return "pdf"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in GIF_EXTS:
        return "gif"
    return "image"


def folder_key(folder: str) -> str:
    """VIEWED / SEEN でフォルダをファイルと区別するためのキー。"""
    return folder + "/"


def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def scan_items() -> None:
    global IMAGES, FOLDERS
    files: dict[str, dict] = {}
    folders: dict[str, dict] = {}
    if not SCREENSHOT_DIR.exists():
        print(f"[warn] {SCREENSHOT_DIR} does not exist")
        IMAGES, FOLDERS = {}, {}
        return
    for p in SCREENSHOT_DIR.iterdir():
        if p.name.startswith("."):
            continue
        try:
            stat = p.stat()
        except OSError:
            continue
        if p.is_dir():
            pages = _scan_folder_pages(p)
            if not pages:
                continue
            folders[p.name] = {"mtime": stat.st_mtime, "files": pages, "sizes": None}
        elif p.is_file() and p.suffix.lower() in ALLOWED_EXTS:
            files[p.name] = {
                "mtime": stat.st_mtime,
                "size": stat.st_size,
                "type": file_type(p.name),
            }
    IMAGES, FOLDERS = files, folders
    update_seen(set(files) | {folder_key(n) for n in folders})
    print(
        f"[info] scanned {len(IMAGES)} files / {len(FOLDERS)} folders "
        f"from {SCREENSHOT_DIR} ({len(NEW_ITEMS)} new)"
    )


def _scan_folder_pages(folder: Path) -> list[str]:
    try:
        names = [
            q.name
            for q in folder.iterdir()
            if q.is_file()
            and not q.name.startswith(".")
            and q.suffix.lower() in PAGE_EXTS
        ]
    except OSError:
        return []
    return sorted(names, key=natural_key)


def load_viewed() -> None:
    global VIEWED
    if VIEWED_FILE.exists():
        try:
            VIEWED = json.loads(VIEWED_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            VIEWED = {}
    else:
        VIEWED = {}


def save_viewed() -> None:
    tmp = VIEWED_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(VIEWED, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(VIEWED_FILE)


def load_seen() -> bool:
    """seen.json を読み込む。ファイルが存在した場合 True を返す。"""
    global SEEN
    if SEEN_FILE.exists():
        try:
            SEEN = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
            return True
        except (json.JSONDecodeError, OSError):
            SEEN = {}
    else:
        SEEN = {}
    return False


def save_seen() -> None:
    tmp = SEEN_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(SEEN, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(SEEN_FILE)


def update_seen(found: set[str]) -> None:
    """今回のスキャンで新たに見つかった項目を NEW_ITEMS に記録し、
    既知一覧 (SEEN) を更新して保存する。"""
    global SEEN, NEW_ITEMS
    # seen.json が存在しなかった初回起動時は、既存項目を「新規」とみなさない。
    first_run = not SEEN_FILE.exists()
    now = datetime.now(timezone.utc).isoformat()
    new_names: set[str] = set()
    for key in found:
        if key not in SEEN:
            SEEN[key] = now
            if not first_run:
                new_names.add(key)
    # 削除された項目を SEEN から取り除く
    for key in list(SEEN):
        if key not in found:
            del SEEN[key]
    NEW_ITEMS = new_names
    save_seen()


def mark_viewed_key(key: str) -> None:
    with VIEWED_LOCK:
        VIEWED[key] = datetime.now(timezone.utc).isoformat()
        save_viewed()


# --- キャッシュ ---------------------------------------------------------


def _cache_path(base: Path, *parts, ext: str) -> Path:
    key = hashlib.sha1("|".join(str(x) for x in parts).encode("utf-8")).hexdigest()
    return base / f"{key}{ext}"


def _atomic_write(dst: Path, write) -> None:
    tmp = dst.with_name(f"{dst.name}.{threading.get_ident()}.tmp")
    try:
        write(tmp)
        tmp.replace(dst)
    finally:
        tmp.unlink(missing_ok=True)


def _save_jpeg(im: Image.Image, dst: Path, quality: int = 85) -> None:
    if im.mode != "RGB":
        if im.mode == "P":
            im = im.convert("RGBA")
        if im.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        else:
            im = im.convert("RGB")
    _atomic_write(dst, lambda tmp: im.save(tmp, "JPEG", quality=quality))


# --- サムネイル ---------------------------------------------------------


def ensure_thumb(src: Path, mtime: float, kind: str) -> Path:
    tp = _cache_path(THUMB_DIR, src, mtime, ext=".jpg")
    if tp.exists():
        return tp
    if kind == "pdf":
        _make_pdf_thumb(src, tp)
    elif kind == "video":
        _make_video_thumb(src, tp)
    else:
        _make_image_thumb(src, tp)
    return tp


def _make_image_thumb(src: Path, dst: Path) -> None:
    with Image.open(src) as im:
        im.thumbnail(THUMB_SIZE)
        _save_jpeg(im, dst)


def _make_pdf_thumb(src: Path, dst: Path) -> None:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(src))
    try:
        pil = pdf[0].render(scale=1.0).to_pil()
    finally:
        pdf.close()
    pil.thumbnail(THUMB_SIZE)
    _save_jpeg(pil, dst)


def _make_video_thumb(src: Path, dst: Path) -> None:
    """ffmpeg で先頭付近のフレームを1枚抜き出してサムネイルにする。
    ffmpeg が無い / 失敗した場合はプレースホルダを生成する。"""
    if FFMPEG:
        scale = (
            f"scale=w={THUMB_SIZE[0]}:h={THUMB_SIZE[1]}"
            ":force_original_aspect_ratio=decrease"
        )
        # 冒頭が黒画面のことがあるので 1 秒地点を優先し、短い動画は先頭に落とす
        for seek in ("1", "0"):
            args = [
                "-ss", seek, "-i", str(src), "-frames:v", "1",
                "-vf", scale, "-f", "image2", "-y",
            ]
            try:
                _atomic_write(dst, lambda tmp: _run_ffmpeg(args + [str(tmp)], tmp))
            except (subprocess.SubprocessError, OSError, RuntimeError):
                continue
            if dst.exists():
                return
    _make_placeholder_thumb(dst)


def _run_ffmpeg(args: list[str], out: Path) -> None:
    subprocess.run(
        [FFMPEG, "-v", "error", "-nostdin", *args],
        check=True,
        timeout=60,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError("ffmpeg produced no frame")


def _make_placeholder_thumb(dst: Path) -> None:
    _save_jpeg(Image.new("RGB", THUMB_SIZE, (34, 34, 34)), dst)


# --- GIF の無限ループ化 -------------------------------------------------

# アプリケーション拡張ブロック: 0x21 0xFF <サイズ11> "NETSCAPE2.0"
NETSCAPE_SIG = b"\x21\xff\x0bNETSCAPE2.0"


def _gif_force_loop(data: bytes) -> bytes | None:
    """GIF のループ回数を無限(0)に書き換えたバイト列を返す。
    再エンコードせずバイト列だけを操作するので画質・フレームは変化しない。
    書き換え不要 / 解析できない場合は None。"""
    if not data.startswith((b"GIF87a", b"GIF89a")):
        return None
    idx = data.find(NETSCAPE_SIG)
    if idx != -1:
        # 続くサブブロック: [サイズ=3][ID=1][ループ回数 下位][上位]
        sub = idx + len(NETSCAPE_SIG)
        if len(data) < sub + 4 or data[sub] != 0x03 or data[sub + 1] != 0x01:
            return None
        if data[sub + 2] == 0 and data[sub + 3] == 0:
            return None  # 既に無限ループ
        return data[: sub + 2] + b"\x00\x00" + data[sub + 4 :]
    # 拡張が無い GIF は1回しか再生されない。論理画面記述子
    # (+ グローバルカラーテーブル) の直後に無限ループの拡張を挿入する。
    if len(data) < 13:
        return None
    packed = data[10]
    gct = 3 * (2 ** ((packed & 0x07) + 1)) if packed & 0x80 else 0
    pos = 13 + gct
    if pos > len(data):
        return None
    block = NETSCAPE_SIG + b"\x03\x01\x00\x00\x00"
    return data[:pos] + block + data[pos:]


def ensure_looping_gif(src: Path, mtime: float) -> Path:
    """無限ループ化した GIF のパスを返す。書き換え不要なら元ファイル。"""
    cache_key = f"{src}|{mtime}"
    if cache_key in GIF_PASSTHROUGH:
        return src
    dst = _cache_path(CACHE_DIR, "gif", src, mtime, ext=".gif")
    if dst.exists():
        return dst
    try:
        data = src.read_bytes()
    except OSError:
        return src
    patched = _gif_force_loop(data)
    if patched is None:
        GIF_PASSTHROUGH.add(cache_key)
        return src
    _atomic_write(dst, lambda tmp: tmp.write_bytes(patched))
    return dst


# --- PDF のページ描画 ---------------------------------------------------


def pdf_page_sizes(name: str) -> list[tuple[float, float]]:
    meta = IMAGES[name]
    if meta.get("page_sizes") is None:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(SCREENSHOT_DIR / name))
        try:
            meta["page_sizes"] = [
                (pdf[i].get_width(), pdf[i].get_height()) for i in range(len(pdf))
            ]
        finally:
            pdf.close()
    return meta["page_sizes"]


def ensure_pdf_page(name: str, index: int) -> Path:
    src = SCREENSHOT_DIR / name
    dst = _cache_path(
        CACHE_DIR, "pdfpage", src, IMAGES[name]["mtime"], index, ext=".jpg"
    )
    if dst.exists():
        return dst
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(src))
    try:
        if not 0 <= index < len(pdf):
            raise HTTPException(404)
        page = pdf[index]
        scale = min(
            PDF_MAX_SCALE, max(1.0, PDF_PAGE_WIDTH / max(1.0, page.get_width()))
        )
        pil = page.render(scale=scale).to_pil()
    finally:
        pdf.close()
    _save_jpeg(pil, dst)
    return dst


def _image_size(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as im:
            return im.size
    except (OSError, Image.DecompressionBombError):
        return (0, 0)


# --- アプリ -------------------------------------------------------------


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_viewed()
    load_seen()
    scan_items()
    if not FFMPEG:
        print("[warn] ffmpeg が見つかりません。動画のサムネイルは代替表示になります")
    print(f"[info] access from same WiFi: http://{get_local_ip()}:{PORT}")
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/items")
def list_items():
    items = []
    for name, meta in IMAGES.items():
        enc = quote(name, safe="")
        items.append(
            {
                "key": name,
                "name": name,
                "type": meta["type"],
                "mtime": meta["mtime"],
                "viewed_at": VIEWED.get(name),
                "is_new": name in NEW_ITEMS,
                "thumb": f"/thumb/{enc}",
                "src": f"/image/{enc}",
                "info": f"/api/pdf/{enc}" if meta["type"] == "pdf" else None,
                "viewed_url": f"/api/viewed/{enc}",
                "count": None,
            }
        )
    for name, meta in FOLDERS.items():
        enc = quote(name, safe="")
        key = folder_key(name)
        items.append(
            {
                "key": key,
                "name": name,
                "type": "folder",
                "mtime": meta["mtime"],
                "viewed_at": VIEWED.get(key),
                "is_new": key in NEW_ITEMS,
                "thumb": f"/folders/{enc}/thumb",
                "src": None,
                "info": f"/api/folders/{enc}",
                "viewed_url": f"/api/folders/{enc}/viewed",
                "count": len(meta["files"]),
            }
        )

    def sort_key(item):
        # 新規追加された項目を最上部に表示する
        if item["is_new"]:
            return (0, -item["mtime"])
        viewed = item["viewed_at"]
        if viewed:
            return (1, -datetime.fromisoformat(viewed).timestamp())
        return (2, -item["mtime"])

    items.sort(key=sort_key)
    return {"items": items}


@app.get("/thumb/{name}")
def get_thumb(name: str):
    meta = IMAGES.get(name)
    if meta is None:
        raise HTTPException(404)
    thumb = ensure_thumb(SCREENSHOT_DIR / name, meta["mtime"], meta["type"])
    return FileResponse(thumb, media_type="image/jpeg")


@app.get("/image/{name}")
def get_image(name: str):
    meta = IMAGES.get(name)
    if meta is None:
        raise HTTPException(404)
    src = SCREENSHOT_DIR / name
    if meta["type"] == "gif":
        return FileResponse(
            ensure_looping_gif(src, meta["mtime"]), media_type="image/gif"
        )
    return FileResponse(src)


@app.get("/api/pdf/{name}")
def get_pdf_info(name: str):
    meta = IMAGES.get(name)
    if meta is None or meta["type"] != "pdf":
        raise HTTPException(404)
    enc = quote(name, safe="")
    return {
        "pages": [
            {"src": f"/pdfpage/{enc}/{i}", "w": w, "h": h}
            for i, (w, h) in enumerate(pdf_page_sizes(name))
        ]
    }


@app.get("/pdfpage/{name}/{index}")
def get_pdf_page(name: str, index: int):
    meta = IMAGES.get(name)
    if meta is None or meta["type"] != "pdf":
        raise HTTPException(404)
    return FileResponse(ensure_pdf_page(name, index), media_type="image/jpeg")


@app.post("/api/viewed/{name}")
def mark_viewed(name: str):
    if name not in IMAGES:
        raise HTTPException(404)
    mark_viewed_key(name)
    return {"ok": True}


@app.get("/api/folders/{folder}")
def get_folder(folder: str):
    meta = FOLDERS.get(folder)
    if meta is None:
        raise HTTPException(404)
    if meta["sizes"] is None:
        meta["sizes"] = [
            _image_size(SCREENSHOT_DIR / folder / n) for n in meta["files"]
        ]
    enc = quote(folder, safe="")
    return {
        "name": folder,
        "pages": [
            {
                "src": f"/folders/{enc}/image/{quote(n, safe='')}",
                "w": size[0],
                "h": size[1],
            }
            for n, size in zip(meta["files"], meta["sizes"])
        ],
    }


@app.get("/folders/{folder}/thumb")
def get_folder_thumb(folder: str):
    meta = FOLDERS.get(folder)
    if meta is None:
        raise HTTPException(404)
    cover = SCREENSHOT_DIR / folder / meta["files"][0]
    try:
        mtime = cover.stat().st_mtime
    except OSError:
        raise HTTPException(404) from None
    return FileResponse(ensure_thumb(cover, mtime, "image"), media_type="image/jpeg")


@app.get("/folders/{folder}/image/{name}")
def get_folder_image(folder: str, name: str):
    meta = FOLDERS.get(folder)
    if meta is None or name not in meta["files"]:
        raise HTTPException(404)
    src = SCREENSHOT_DIR / folder / name
    if src.suffix.lower() in GIF_EXTS:
        try:
            mtime = src.stat().st_mtime
        except OSError:
            raise HTTPException(404) from None
        return FileResponse(ensure_looping_gif(src, mtime), media_type="image/gif")
    return FileResponse(src)


@app.post("/api/folders/{folder}/viewed")
def mark_folder_viewed(folder: str):
    if folder not in FOLDERS:
        raise HTTPException(404)
    mark_viewed_key(folder_key(folder))
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
