"""
plugins/fichiers/storage.py — SCRIBE
=====================================
Stockage *content-addressed* des blobs du drive interne SCRIBE.

Principes (cf. SCRIBE_PROMPT_plugin_fichiers §5) :
  - Les blobs vivent SOUS ``SCRIBE_DATA_DIR`` (persiste entre builds, capturé
    par le backup), JAMAIS dans le dossier de build.
  - Nom de fichier = empreinte SHA-256 → déduplication + intégrité vérifiable.
  - Écriture en streaming chunké : le fichier entier n'est jamais chargé en
    mémoire.
  - La DB ne stocke que des MÉTADONNÉES + le chemin ; jamais de binaire.

Emplacement : ``SCRIBE_DATA_DIR/fichiers/blobs/<2 premiers car. du checksum>/<checksum>``
Repli si ``SCRIBE_DATA_DIR`` non défini : ``<racine projet>/data/fichiers``.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
import tempfile
from typing import BinaryIO, Iterator, Tuple

# Taille de lecture/écriture en streaming (256 Ko)
CHUNK = 256 * 1024


def _data_root() -> pathlib.Path:
    base = os.environ.get("SCRIBE_DATA_DIR")
    if base:
        root = pathlib.Path(base)
    else:
        # Racine projet = parent de plugins/
        root = pathlib.Path(__file__).resolve().parents[2] / "data"
    return root / "fichiers"


def blobs_dir() -> pathlib.Path:
    d = _data_root() / "blobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path_for(checksum: str) -> pathlib.Path:
    sub = blobs_dir() / checksum[:2]
    sub.mkdir(parents=True, exist_ok=True)
    return sub / checksum


def store_stream(src: BinaryIO, max_bytes: int | None = None) -> Tuple[str, int, str]:
    """Écrit ``src`` en streaming dans un fichier temporaire, calcule le
    checksum SHA-256 à la volée, puis déplace le blob à son emplacement final
    content-addressed (dédup : si déjà présent, le temporaire est supprimé).

    Retourne ``(checksum, taille, chemin_relatif)``.
    Lève ``ValueError("quota")`` si ``max_bytes`` est dépassé.
    """
    h = hashlib.sha256()
    taille = 0
    tmp_fd, tmp_name = tempfile.mkstemp(prefix="scribe_fich_", dir=str(blobs_dir()))
    try:
        with os.fdopen(tmp_fd, "wb") as out:
            while True:
                chunk = src.read(CHUNK)
                if not chunk:
                    break
                taille += len(chunk)
                if max_bytes is not None and taille > max_bytes:
                    raise ValueError("quota")
                h.update(chunk)
                out.write(chunk)
        checksum = h.hexdigest()
        final = _path_for(checksum)
        if final.exists():
            # Blob déjà stocké (dédup) → on jette le temporaire
            os.unlink(tmp_name)
        else:
            shutil.move(tmp_name, str(final))
        rel = str(final.relative_to(_data_root()))
        return checksum, taille, rel
    except Exception:
        try:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except Exception:
            pass
        raise


def blob_path(checksum: str) -> pathlib.Path:
    return _path_for(checksum)


def open_blob(checksum: str) -> BinaryIO:
    return open(_path_for(checksum), "rb")


def iter_blob(checksum: str) -> Iterator[bytes]:
    with open_blob(checksum) as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            yield chunk


def delete_blob(checksum: str) -> bool:
    """Supprime physiquement un blob. Retourne True si le fichier existait."""
    p = _path_for(checksum)
    try:
        if p.exists():
            p.unlink()
            return True
    except Exception:
        pass
    return False


def purge_orphans(referenced_checksums: set[str]) -> int:
    """Supprime tout blob sur disque non référencé par un Fichier (RGPD : pas
    de binaire résiduel). Retourne le nombre de blobs purgés."""
    n = 0
    root = blobs_dir()
    if not root.exists():
        return 0
    for sub in root.iterdir():
        if not sub.is_dir():
            continue
        for f in sub.iterdir():
            if f.is_file() and f.name not in referenced_checksums:
                try:
                    f.unlink()
                    n += 1
                except Exception:
                    pass
    return n
