from __future__ import annotations

import hashlib
import json
import socket
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

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
VIEWED_FILE = BASE_DIR / "viewed.json"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
PDF_EXTS = {".pdf"}
ALLOWED_EXTS = IMAGE_EXTS | PDF_EXTS
THUMB_SIZE = (300, 300)
PORT = 8000


def file_type(name: str) -> str:
    return "pdf" if Path(name).suffix.lower() in PDF_EXTS else "image"

THUMB_DIR.mkdir(exist_ok=True)

IMAGES: dict[str, dict] = {}
VIEWED: dict[str, str] = {}
VIEWED_LOCK = threading.Lock()


def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def scan_images() -> None:
    global IMAGES
    found: dict[str, dict] = {}
    if not SCREENSHOT_DIR.exists():
        print(f"[warn] {SCREENSHOT_DIR} does not exist")
        IMAGES = {}
        return
    for p in SCREENSHOT_DIR.iterdir():
        if not p.is_file() or p.suffix.lower() not in ALLOWED_EXTS:
            continue
        try:
            stat = p.stat()
        except OSError:
            continue
        found[p.name] = {"mtime": stat.st_mtime, "size": stat.st_size}
    IMAGES = found
    print(f"[info] scanned {len(IMAGES)} images from {SCREENSHOT_DIR}")


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


def thumb_path_for(name: str) -> Path:
    mtime = IMAGES[name]["mtime"]
    key = hashlib.sha1(f"{name}|{mtime}".encode("utf-8")).hexdigest()
    return THUMB_DIR / f"{key}.jpg"


def ensure_thumb(name: str) -> Path:
    tp = thumb_path_for(name)
    if tp.exists():
        return tp
    src = SCREENSHOT_DIR / name
    if src.suffix.lower() in PDF_EXTS:
        _make_pdf_thumb(src, tp)
    else:
        _make_image_thumb(src, tp)
    return tp


def _make_image_thumb(src: Path, dst: Path) -> None:
    with Image.open(src) as im:
        im.thumbnail(THUMB_SIZE)
        if im.mode != "RGB":
            if im.mode == "P":
                im = im.convert("RGBA")
            if im.mode in ("RGBA", "LA"):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1])
                im = bg
            else:
                im = im.convert("RGB")
        im.save(dst, "JPEG", quality=85)


def _make_pdf_thumb(src: Path, dst: Path) -> None:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(src))
    try:
        pil = pdf[0].render(scale=1.0).to_pil()
    finally:
        pdf.close()
    pil.thumbnail(THUMB_SIZE)
    if pil.mode != "RGB":
        pil = pil.convert("RGB")
    pil.save(dst, "JPEG", quality=85)


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_viewed()
    scan_images()
    print(f"[info] access from same WiFi: http://{get_local_ip()}:{PORT}")
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/images")
def list_images():
    items = []
    for name, meta in IMAGES.items():
        items.append(
            {
                "name": name,
                "type": file_type(name),
                "mtime": meta["mtime"],
                "viewed_at": VIEWED.get(name),
            }
        )

    def sort_key(item):
        viewed = item["viewed_at"]
        if viewed:
            return (0, -datetime.fromisoformat(viewed).timestamp())
        return (1, -item["mtime"])

    items.sort(key=sort_key)
    return {"images": items}


@app.get("/thumb/{name}")
def get_thumb(name: str):
    if name not in IMAGES:
        raise HTTPException(404)
    return FileResponse(ensure_thumb(name), media_type="image/jpeg")


@app.get("/image/{name}")
def get_image(name: str):
    if name not in IMAGES:
        raise HTTPException(404)
    return FileResponse(SCREENSHOT_DIR / name)


@app.post("/api/viewed/{name}")
def mark_viewed(name: str):
    if name not in IMAGES:
        raise HTTPException(404)
    with VIEWED_LOCK:
        VIEWED[name] = datetime.now(timezone.utc).isoformat()
        save_viewed()
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
