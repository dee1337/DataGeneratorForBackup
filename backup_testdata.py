#!/usr/bin/env python3
"""Backup-Testdaten-Generator mit Manifesten und SHA-256-Restore-Pruefung.

Beispiele:
  python backup_testdata.py create ./testdata --size 10GB --profile mixed
  python backup_testdata.py mutate ./testdata --change 5 --delete 1 --add 2GB
  python backup_testdata.py manifest ./testdata --label vor_restore
  python backup_testdata.py verify ./restore --manifest ./testdata/.backup_manifests/manifest_vor_restore.json

Ablauf Szenarien:

1. Baseline-Datensatz erzeugen
python backup_testdata.py create ./testdata --size 1GB --profile fileserver --data mixed --label baseline

Das Manifest wird dabei hier abgelegt:  testdata/.backup_manifests/manifest_baseline.json 

2. Full Backup durchführen
Ordner testdata, einschließlich .backup_manifests sichern.

python backup_testdata.py mutate ./testdata --change 5 --delete 2 --add 1GB --label incremental_01

3. Incremental-Szenario erzeugen (INT Werte in Parameter sind Prozente)
python backup_testdata.py mutate ./testdata --change 5 --delete 2 --add 1GB --label incremental_01

Danach existiert zusätzlich: testdata/.backup_manifests/manifest_incremental_01.json

Erläuterung der Parameter im Detail:
    --delete 2

    Wählt zufällig 2 % der vorhandenen Dateien aus.
    Diese Dateien werden tatsächlich gelöscht.
    Bei 10.000 Dateien wären das 200 Dateien.

    --change 5

    Danach wird die verbleibende Dateiliste neu eingelesen.
    Von diesen Dateien werden zufällig 5 % ausgewählt.
    In jeder ausgewählten Datei verändert das Skript bis zu 1 MB Daten an einer zufälligen Position.
    Wichtig: Eine 100-GB-Datei wird also nicht zu 5 % verändert. 5 bedeutet 5 % der Dateien.

    --add 1GB

    Erstellt zusätzlich insgesamt 1 GB neue Zufallsdaten.
    Diese landen unter: ./testdata/incremental_new/

    --label incremental_01

    Anschließend wird der komplette aktuelle Datenbestand erneut per SHA-256 gehasht.
    Das Ergebnis landet beispielsweise in: .backup_manifests/manifest_incremental_01.json


4. Restore prüfen
Wenn das Backup beispielsweise nach ./restore-test wiederhergestellt wurde:

python backup_testdata.py verify ./restore-test  --manifest ./restore-test/.backup_manifests/manifest_baseline.json

Wichtig: Das Baseline-Manifest passt nur zum ursprünglichen Full-Backup-Stand. 
Für den Stand nach der Mutation muss manifest_incremental_01.json verwendet werden

Bei einer beschädigten oder veränderten Datei werden Fehler angezeigt.
Parallel wird ein detaillierter Report in folgendem Format angelegt: restore_verification_20261021_101500.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

VERSION = "2.0"
CHUNK_SIZE = 8 * 1024**2
MANIFEST_DIR = ".backup_manifests"
LATEST_FILE = "latest.txt"
SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(B|KB|MB|GB|TB)\s*$", re.I)
UNITS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}

PROFILES = {
    "mixed": [
        (1 * 1024, 100 * 1024, 0.15),
        (100 * 1024, 5 * 1024**2, 0.30),
        (5 * 1024**2, 100 * 1024**2, 0.35),
        (100 * 1024**2, 2 * 1024**3, 0.20),
    ],
    "fileserver": [
        (1 * 1024, 100 * 1024, 0.40),
        (100 * 1024, 5 * 1024**2, 0.40),
        (5 * 1024**2, 100 * 1024**2, 0.15),
        (100 * 1024**2, 1 * 1024**3, 0.05),
    ],
    "large": [(1 * 1024**3, 10 * 1024**3, 1.0)],
}


def parse_size(value: str) -> int:
    match = SIZE_RE.match(value)
    if not match:
        raise argparse.ArgumentTypeError(
            f"Ungueltige Groesse: {value}. Beispiele: 500MB, 10GB, 1TB"
        )
    return int(float(match.group(1)) * UNITS[match.group(2).upper()])


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_label(label: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", label.strip()).strip("._")
    return cleaned or datetime.now().strftime("%Y%m%d_%H%M%S")


def is_manifest_path(root: Path, path: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    return bool(rel.parts and rel.parts[0] == MANIFEST_DIR)


def iter_data_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if (
            path.is_file()
            and not is_manifest_path(root, path)
            and not path.name.startswith("restore_verification_")
        ):
            yield path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_random_file(path: Path, size: int) -> None:
    with path.open("wb", buffering=0) as handle:
        remaining = size
        while remaining:
            amount = min(CHUNK_SIZE, remaining)
            handle.write(os.urandom(amount))
            remaining -= amount


def write_compressible_file(path: Path, size: int) -> None:
    pattern = b"BACKUP-TEST-DATA-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ\n"
    block = (pattern * (CHUNK_SIZE // len(pattern) + 1))[:CHUNK_SIZE]
    with path.open("wb", buffering=0) as handle:
        remaining = size
        while remaining:
            amount = min(CHUNK_SIZE, remaining)
            handle.write(block[:amount])
            remaining -= amount


def write_sparse_file(path: Path, size: int) -> None:
    with path.open("wb") as handle:
        handle.truncate(size)


def choose_file_size(profile_name: str, remaining: int) -> int:
    value = random.random()
    cumulative = 0.0
    for minimum, maximum, weight in PROFILES[profile_name]:
        cumulative += weight
        if value <= cumulative:
            maximum = min(maximum, remaining)
            return remaining if maximum < minimum else random.randint(minimum, maximum)
    return min(remaining, PROFILES[profile_name][-1][1])


def latest_manifest(root: Path) -> Path:
    manifest_dir = root / MANIFEST_DIR
    pointer = manifest_dir / LATEST_FILE
    if pointer.exists():
        candidate = manifest_dir / pointer.read_text(encoding="utf-8").strip()
        if candidate.is_file():
            return candidate
    candidates = sorted(manifest_dir.glob("manifest_*.json"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"Kein Manifest unter {manifest_dir} gefunden.")
    return candidates[-1]


def create_manifest(root: Path, label: str | None = None) -> Path:
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Datenverzeichnis existiert nicht: {root}")

    label = safe_label(label or datetime.now().strftime("%Y%m%d_%H%M%S"))
    manifest_dir = root / MANIFEST_DIR
    manifest_dir.mkdir(parents=True, exist_ok=True)
    output = manifest_dir / f"manifest_{label}.json"
    temp = manifest_dir / f".{output.name}.tmp"

    if output.exists():
        raise FileExistsError(f"Manifest existiert bereits: {output}")

    files = sorted(iter_data_files(root), key=lambda p: p.relative_to(root).as_posix())
    entries = []
    total = 0
    started = time.time()

    print(f"Erzeuge Manifest und SHA-256 fuer {len(files)} Dateien ...")
    for index, path in enumerate(files, 1):
        stat = path.stat()
        rel = path.relative_to(root).as_posix()
        digest = sha256_file(path)
        entries.append({
            "path": rel,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": digest,
        })
        total += stat.st_size
        print(f"\r{index:8d}/{len(files):8d} | {human_size(total):>12} | {rel[:60]}", end="", flush=True)

    manifest = {
        "schema": "backup-test-manifest-v1",
        "generator_version": VERSION,
        "created_utc": utc_now(),
        "label": label,
        "algorithm": "SHA-256",
        "root_name": root.name,
        "file_count": len(entries),
        "total_bytes": total,
        "files": entries,
    }

    temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, output)
    (manifest_dir / LATEST_FILE).write_text(output.name + "\n", encoding="utf-8")
    print(f"\nManifest: {output}")
    print(f"Geprueft: {len(entries)} Dateien, {human_size(total)}, {time.time() - started:.1f} s")
    return output


def create_dataset(target: Path, total_size: int, profile: str, data_mode: str, label: str) -> None:
    target = target.resolve()
    target.mkdir(parents=True, exist_ok=True)
    existing = list(iter_data_files(target))
    if existing:
        raise RuntimeError(f"Ziel enthaelt bereits {len(existing)} Datendateien: {target}")

    created = 0
    counter = 1
    started = time.time()
    print(f"Ziel: {target}\nGroesse: {human_size(total_size)}\nProfil: {profile}\nDaten: {data_mode}\n")

    while created < total_size:
        remaining = total_size - created
        file_size = choose_file_size(profile, remaining)
        folder = target / f"set_{counter // 1000:04d}"
        folder.mkdir(exist_ok=True)
        path = folder / f"file_{counter:08d}.bin"
        mode = random.choices(["random", "compressible"], weights=[60, 40], k=1)[0] if data_mode == "mixed" else data_mode
        print(f"\r{counter:8d} Dateien | {human_size(created):>12}/{human_size(total_size):>12} | {mode:12}", end="", flush=True)
        {"random": write_random_file, "compressible": write_compressible_file, "sparse": write_sparse_file}[mode](path, file_size)
        created += file_size
        counter += 1

    print(f"\nErzeugt: {counter - 1} Dateien, {human_size(created)}, {time.time() - started:.1f} s")
    create_manifest(target, label)


def mutate_dataset(target: Path, change_pct: float, delete_pct: float, add_size: int, label: str) -> None:
    target = target.resolve()
    files = list(iter_data_files(target))
    if not files:
        raise RuntimeError("Keine Testdateien gefunden.")
    if not 0 <= change_pct <= 100 or not 0 <= delete_pct <= 100:
        raise ValueError("--change und --delete muessen zwischen 0 und 100 liegen.")

    delete_count = min(len(files), int(len(files) * delete_pct / 100))
    for path in random.sample(files, delete_count):
        path.unlink()

    files = list(iter_data_files(target))
    change_count = min(len(files), int(len(files) * change_pct / 100))
    changed_bytes = 0
    for path in random.sample(files, change_count):
        size = path.stat().st_size
        if size == 0:
            continue
        amount = min(size, 1024**2)
        offset = random.randint(0, max(0, size - amount))
        with path.open("r+b") as handle:
            handle.seek(offset)
            handle.write(os.urandom(amount))
        changed_bytes += amount

    if add_size > 0:
        add_dir = target / "incremental_new"
        add_dir.mkdir(exist_ok=True)
        remaining = add_size
        counter = time.time_ns()
        while remaining:
            chunk = min(remaining, random.randint(10 * 1024**2, 500 * 1024**2))
            write_random_file(add_dir / f"new_{counter}.bin", chunk)
            remaining -= chunk
            counter += 1

    print(f"Geloescht: {delete_count}; veraendert: {change_count} ({human_size(changed_bytes)}); hinzugefuegt: {human_size(add_size)}")
    create_manifest(target, label)


def verify_dataset(restored_root: Path, manifest_path: Path | None, check_extra: bool) -> int:
    restored_root = restored_root.resolve()
    manifest_path = manifest_path.resolve() if manifest_path else latest_manifest(restored_root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "backup-test-manifest-v1" or manifest.get("algorithm") != "SHA-256":
        raise ValueError("Nicht unterstuetztes oder ungueltiges Manifest.")

    expected = {entry["path"]: entry for entry in manifest["files"]}
    actual_rel = {p.relative_to(restored_root).as_posix() for p in iter_data_files(restored_root)} if check_extra else set()
    missing, size_errors, hash_errors, io_errors = [], [], [], []
    verified_bytes = 0
    started = time.time()

    print(f"Restore:  {restored_root}\nManifest: {manifest_path}\nAlgorithmus: SHA-256\n")
    for index, (rel, entry) in enumerate(expected.items(), 1):
        path = restored_root / Path(rel)
        print(f"\r{index:8d}/{len(expected):8d} | {human_size(verified_bytes):>12} | {rel[:60]}", end="", flush=True)
        if not path.is_file():
            missing.append(rel)
            continue
        try:
            size = path.stat().st_size
            if size != entry["size"]:
                size_errors.append({"path": rel, "expected": entry["size"], "actual": size})
                continue
            digest = sha256_file(path)
            verified_bytes += size
            if digest != entry["sha256"]:
                hash_errors.append({"path": rel, "expected": entry["sha256"], "actual": digest})
        except OSError as exc:
            io_errors.append({"path": rel, "error": str(exc)})

    extra = sorted(actual_rel - set(expected)) if check_extra else []
    report = {
        "schema": "backup-restore-verification-v1",
        "verified_utc": utc_now(),
        "restore_root": str(restored_root),
        "manifest": str(manifest_path),
        "expected_files": len(expected),
        "verified_bytes": verified_bytes,
        "missing": missing,
        "size_mismatches": size_errors,
        "hash_mismatches": hash_errors,
        "io_errors": io_errors,
        "extra_files": extra,
        "success": not (missing or size_errors or hash_errors or io_errors or extra),
    }
    report_path = restored_root / f"restore_verification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n")
    print("RESTORE-PRUEFUNG BESTANDEN" if report["success"] else "RESTORE-PRUEFUNG FEHLGESCHLAGEN")
    print(f"Erwartet:          {len(expected)} Dateien")
    print(f"Verifizierte Daten:{human_size(verified_bytes):>12}")
    print(f"Fehlend:           {len(missing)}")
    print(f"Groessenfehler:    {len(size_errors)}")
    print(f"SHA-256-Fehler:    {len(hash_errors)}")
    print(f"Lesefehler:        {len(io_errors)}")
    print(f"Zusaetzliche:      {len(extra)}")
    print(f"Dauer:              {time.time() - started:.1f} s")
    print(f"Report:             {report_path}")
    return 0 if report["success"] else 2


def clean_dataset(target: Path) -> None:
    target = target.resolve()
    if not target.exists():
        print("Verzeichnis existiert nicht.")
        return
    confirmation = input(f"Zum Loeschen von {target} exakt DELETE eingeben: ")
    if confirmation != "DELETE":
        print("Abgebrochen.")
        return
    shutil.rmtree(target)
    print("Testdaten geloescht.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generator und Restore-Pruefer fuer Backup-Testdaten")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Datensatz plus SHA-256-Manifest erzeugen")
    create.add_argument("target", type=Path)
    create.add_argument("--size", required=True, type=parse_size)
    create.add_argument("--profile", choices=PROFILES, default="mixed")
    create.add_argument("--data", choices=["random", "compressible", "mixed", "sparse"], default="mixed")
    create.add_argument("--seed", type=int)
    create.add_argument("--label", default="baseline")

    mutate = sub.add_parser("mutate", help="Daten veraendern und neues Manifest erzeugen")
    mutate.add_argument("target", type=Path)
    mutate.add_argument("--change", type=float, default=5)
    mutate.add_argument("--delete", type=float, default=1)
    mutate.add_argument("--add", type=parse_size, default=0)
    mutate.add_argument("--seed", type=int)
    mutate.add_argument("--label")

    manifest = sub.add_parser("manifest", help="Neuen SHA-256-Snapshot erzeugen")
    manifest.add_argument("target", type=Path)
    manifest.add_argument("--label")

    verify = sub.add_parser("verify", help="Restore bytegenau gegen Manifest pruefen")
    verify.add_argument("target", type=Path, help="Wurzel des wiederhergestellten Datenbestands")
    verify.add_argument("--manifest", type=Path, help="Manifestdatei; sonst neuestes Manifest im Ziel")
    verify.add_argument("--ignore-extra", action="store_true", help="Zusaetzliche Dateien nicht als Fehler werten")

    clean = sub.add_parser("clean", help="Testdatensatz loeschen")
    clean.add_argument("target", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if getattr(args, "seed", None) is not None:
            random.seed(args.seed)
        if args.command == "create":
            create_dataset(args.target, args.size, args.profile, args.data, args.label)
        elif args.command == "mutate":
            label = args.label if isinstance(args.label, str) else datetime.now().strftime("incremental_%Y%m%d_%H%M%S")
            mutate_dataset(args.target, args.change, args.delete, args.add, label)
        elif args.command == "manifest":
            create_manifest(args.target, args.label)
        elif args.command == "verify":
            return verify_dataset(args.target, args.manifest, not args.ignore_extra)
        elif args.command == "clean":
            clean_dataset(args.target)
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
