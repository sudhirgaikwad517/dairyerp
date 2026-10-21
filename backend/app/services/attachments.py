"""Stores uploaded photos safely: only real images, resized, re-encoded as JPEG (drops EXIF/GPS data)."""
import io
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from backend.app.models.entities import Attachment

# Photos are kept outside the database; DAIRY_UPLOAD_DIR can point elsewhere (e.g. a backed-up drive)
UPLOAD_ROOT = Path(os.getenv("DAIRY_UPLOAD_DIR") or Path(__file__).resolve().parents[3] / "uploads")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB per photo as uploaded
MAX_SIDE = 1600  # pixels; enough to read a pouch label, small enough to store
MAX_PHOTOS = 5

Image.MAX_IMAGE_PIXELS = 40_000_000  # refuse decompression bombs


async def save_photo(db: Session, upload: UploadFile, owner_type: str, owner_id: int, user_id: int) -> Attachment:
    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Photo is too large (max 10 MB)")
    if not data:
        raise HTTPException(status_code=400, detail="Empty photo")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(status_code=400, detail="Please upload a photo (JPG or PNG)")

    img = ImageOps.exif_transpose(img)  # keep phone photos the right way up
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))

    now = datetime.utcnow()
    rel = Path(owner_type) / f"{now:%Y}" / f"{now:%m}" / f"{uuid.uuid4().hex}.jpg"
    dest = UPLOAD_ROOT / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "JPEG", quality=82, optimize=True)  # re-encoding drops EXIF metadata

    att = Attachment(owner_type=owner_type, owner_id=owner_id, file_path=rel.as_posix(),
                     content_type="image/jpeg", uploaded_by=user_id)
    db.add(att)
    db.flush()
    return att


async def save_photos(db: Session, uploads: List[UploadFile], owner_type: str, owner_id: int, user_id: int) -> List[Attachment]:
    files = [u for u in (uploads or []) if u and u.filename]
    if len(files) > MAX_PHOTOS:
        raise HTTPException(status_code=400, detail=f"At most {MAX_PHOTOS} photos")
    return [await save_photo(db, f, owner_type, owner_id, user_id) for f in files]


def attachments_for(db: Session, owner_type: str, owner_id: int) -> List[Attachment]:
    return db.query(Attachment).filter(
        Attachment.owner_type == owner_type, Attachment.owner_id == owner_id
    ).order_by(Attachment.id).all()


def attachment_path(att: Attachment) -> Path:
    path = (UPLOAD_ROOT / att.file_path).resolve()
    if UPLOAD_ROOT.resolve() not in path.parents:
        raise HTTPException(status_code=404, detail="File not found")
    return path
