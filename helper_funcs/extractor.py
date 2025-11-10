"""Archive extraction — ZIP, RAR, 7z, TAR with password support."""
import os
import asyncio
import logging
import tempfile
import shutil
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = (
    ".zip", ".rar", ".7z",
    ".tar", ".tar.gz", ".tgz",
    ".tar.bz2", ".tar.xz", ".gz"
)


# is_archive
def is_archive(filename: str) -> bool:
    lower = filename.lower()
    return any(lower.endswith(ext) for ext in SUPPORTED_FORMATS)


async def extract_archive(
    file_path: str,
    extract_dir: str,
    password: Optional[str] = None,
    status_msg=None
) -> Tuple[bool, str, List[str]]:
    """
    Extract *file_path* into *extract_dir*.
    Returns (success, error_message, list_of_extracted_files).
    """
    os.makedirs(extract_dir, exist_ok=True)
    filename = os.path.basename(file_path).lower()

    async def _edit(text):
        if status_msg:
            try:
                await status_msg.edit(text)
            except Exception:
                pass

    await _edit("📦 **Extracting archive…** Please wait.")

    loop       = asyncio.get_event_loop()
    error_msg  = ""
    success    = False

    # ── ZIP ─────────────────────────────────────────────────────────────
    if filename.endswith(".zip"):
        def _unzip():
            import zipfile
            try:
                with zipfile.ZipFile(file_path, "r") as zf:
                    if password:
                        zf.extractall(extract_dir, pwd=password.encode())
                    else:
                        zf.extractall(extract_dir)
                return True, ""
            except zipfile.BadZipFile as e:
                return False, f"Bad ZIP file: {e}"
            except RuntimeError as e:
                return False, f"ZIP error (wrong password?): {e}"
            except Exception as e:
                return False, str(e)

        success, error_msg = await loop.run_in_executor(None, _unzip)

    # ── RAR ─────────────────────────────────────────────────────────────
    elif filename.endswith(".rar"):
        def _unrar():
            try:
                import rarfile
                with rarfile.RarFile(file_path) as rf:
                    if password:
                        rf.setpassword(password)
                    rf.extractall(extract_dir)
                return True, ""
            except Exception as e:
                # Fallback to system unrar
                cmd = ["unrar", "x", "-y"]
                if password:
                    cmd.append(f"-p{password}")
                cmd += [file_path, extract_dir + "/"]
                result = __import__("subprocess").run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    return True, ""
                return False, result.stderr or str(e)

        success, error_msg = await loop.run_in_executor(None, _unrar)

    # ── 7-Zip ────────────────────────────────────────────────────────────
    elif filename.endswith(".7z"):
        def _un7z():
            cmd = ["7z", "x", "-y", f"-o{extract_dir}"]
            if password:
                cmd.append(f"-p{password}")
            cmd.append(file_path)
            result = __import__("subprocess").run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return True, ""
            return False, result.stderr or "7z extraction failed"

        success, error_msg = await loop.run_in_executor(None, _un7z)

    # ── TAR variants ─────────────────────────────────────────────────────
    elif any(filename.endswith(ext) for ext in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".gz")):
        def _untar():
            import tarfile
            try:
                with tarfile.open(file_path, "r:*") as tf:
                    tf.extractall(extract_dir)
                return True, ""
            except Exception as e:
                return False, str(e)

        success, error_msg = await loop.run_in_executor(None, _untar)

    else:
        return False, f"Unsupported format: {filename}", []

    if not success:
        return False, error_msg, []

    # Collect extracted files
    extracted = []
    for root, _, files in os.walk(extract_dir):
        for fname in files:
            extracted.append(os.path.join(root, fname))

    await _edit(f"✅ Extracted **{len(extracted)}** file(s)!")
    return True, "", extracted


async def list_archive_contents(file_path: str) -> Tuple[bool, str, List[str]]:
    """
    List files inside an archive without extracting.
    Returns (success, error, list_of_names).
    """
    filename = os.path.basename(file_path).lower()

    def _list():
        names = []
        try:
            if filename.endswith(".zip"):
                import zipfile
                with zipfile.ZipFile(file_path, "r") as zf:
                    names = zf.namelist()
            elif filename.endswith(".rar"):
                import rarfile
                with rarfile.RarFile(file_path) as rf:
                    names = [f.filename for f in rf.infolist()]
            elif filename.endswith(".7z"):
                import py7zr
                with py7zr.SevenZipFile(file_path, mode="r") as z:
                    names = z.getnames()
            elif any(filename.endswith(e) for e in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")):
                import tarfile
                with tarfile.open(file_path, "r:*") as tf:
                    names = tf.getnames()
            return True, "", names
        except Exception as e:
            return False, str(e), []

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _list)


def is_password_protected(file_path: str) -> bool:
    """Quick check if an archive needs a password (ZIP / RAR only)."""
    filename = os.path.basename(file_path).lower()
    try:
        if filename.endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(file_path) as zf:
                for info in zf.infolist():
                    if info.flag_bits & 0x1:
                        return True
        elif filename.endswith(".rar"):
            import rarfile
            with rarfile.RarFile(file_path) as rf:
                return rf.needs_password()
    except Exception:
        pass
    return False
