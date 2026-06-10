import os
import hashlib
import logging
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(os.environ.get("ASSETS_DIR", "/app/assets"))
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".pdf", ".zip"}
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


def _url_to_filename(url: str) -> str:
    parsed = urlparse(url)
    basename = Path(parsed.path).name
    if not basename or "." not in basename:
        ext = ".jpg"
        basename = hashlib.md5(url.encode()).hexdigest()[:12] + ext
    return basename


def _safe_ext(filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS


def download_assets(urls: list[str], subfolder: str = "brands") -> list[dict]:
    """
    Download a list of asset URLs into ASSETS_DIR/subfolder/.
    Returns a list of dicts: {url, local_path, size_bytes, success, error}
    """
    dest_dir = ASSETS_DIR / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)

    results = []

    for url in urls:
        result = {"url": url, "local_path": None, "size_bytes": 0, "success": False, "error": None}

        try:
            filename = _url_to_filename(url)

            if not _safe_ext(filename):
                result["error"] = f"Blocked extension: {Path(filename).suffix}"
                results.append(result)
                continue

            dest_path = dest_dir / filename

            if dest_path.exists():
                result["local_path"] = str(dest_path)
                result["size_bytes"] = dest_path.stat().st_size
                result["success"] = True
                results.append(result)
                continue

            with httpx.Client(timeout=30, follow_redirects=True) as client:
                with client.stream("GET", url) as resp:
                    resp.raise_for_status()

                    content_length = int(resp.headers.get("content-length", 0))
                    if content_length > MAX_FILE_SIZE_BYTES:
                        result["error"] = f"File too large: {content_length} bytes"
                        results.append(result)
                        continue

                    ct = resp.headers.get("content-type", "")
                    ext_from_ct = mimetypes.guess_extension(ct.split(";")[0].strip())
                    if ext_from_ct and not _safe_ext("file" + ext_from_ct):
                        result["error"] = f"Blocked content-type: {ct}"
                        results.append(result)
                        continue

                    downloaded = 0
                    with open(dest_path, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=8192):
                            downloaded += len(chunk)
                            if downloaded > MAX_FILE_SIZE_BYTES:
                                dest_path.unlink(missing_ok=True)
                                result["error"] = "File exceeded size limit during download"
                                break
                            f.write(chunk)
                        else:
                            result["local_path"] = str(dest_path)
                            result["size_bytes"] = downloaded
                            result["success"] = True

        except httpx.HTTPStatusError as e:
            result["error"] = f"HTTP {e.response.status_code}"
        except httpx.RequestError as e:
            result["error"] = f"Network error: {str(e)}"
        except Exception as e:
            result["error"] = str(e)

        results.append(result)

    return results


def list_assets(subfolder: str = "") -> list[dict]:
    """List all downloaded assets, optionally filtered by subfolder."""
    root = ASSETS_DIR / subfolder if subfolder else ASSETS_DIR
    if not root.exists():
        return []

    assets = []
    for path in root.rglob("*"):
        if path.is_file() and _safe_ext(path.name):
            assets.append({
                "path": str(path),
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "subfolder": str(path.relative_to(ASSETS_DIR).parent),
            })

    return assets
