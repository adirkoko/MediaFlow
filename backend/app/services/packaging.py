from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OutputSelection:
    path: Path
    output_type: str   # "mp3"/"mp4"/"zip"/...


class OutputPackager:
    def zip_outputs(self, out_dir: Path, zip_path: Path, allowed_ext: set[str]) -> OutputSelection:
        if zip_path.exists():
            zip_path.unlink()

        files = [
            p for p in out_dir.iterdir()
            if p.is_file()
            and p.suffix.lower() in allowed_ext
            and p.name != zip_path.name
        ]
        if not files:
            raise RuntimeError("No output files to zip")

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in files:
                zf.write(p, arcname=p.name)

        return OutputSelection(path=zip_path, output_type="zip")

    def pick_first(self, out_dir: Path, exts: set[str]) -> OutputSelection:
        for p in sorted(out_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in exts:
                return OutputSelection(path=p, output_type=p.suffix.lower().lstrip("."))
        raise RuntimeError("No output file produced")
    

    def zip_files(self, zip_path: Path, files: list[Path]) -> OutputSelection:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        if zip_path.exists():
            zip_path.unlink()

        existing = [p for p in files if p.exists() and p.is_file()]
        if not existing:
            raise RuntimeError("No files to zip")

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in existing:
                zf.write(p, arcname=p.name)

        return OutputSelection(path=zip_path, output_type="zip")
