from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import zipfile
from pathlib import Path


APP_DIRECTORIES = ("02_processed_data", "05_src", "library")
APP_FILES = ("README.md", "requirements-lock.txt")
REFERENCE_PDF_NAME = "ППРк_Труженников пер (1).pdf".casefold()
REFERENCE_PDF_SHA256 = "d586d1840d221c96041db449b7d6868824a328e66b25a21c6e6bee0fa4410392"


def _ignore_generated(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name == "__pycache__"
        or name.casefold() == REFERENCE_PDF_NAME
        or (name.lower().endswith('.pdf')
            and (Path(_directory) / name).is_file()
            and hashlib.sha256((Path(_directory) / name).read_bytes()).hexdigest() == REFERENCE_PDF_SHA256)
        or name in {".pytest_cache", ".mypy_cache", ".ruff_cache"}
        or name.endswith((".pyc", ".pyo"))
    }


def _write_archive(release_dir: Path, archive: Path) -> None:
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as package:
        for path in sorted(release_dir.rglob("*")):
            if path.is_file():
                package.write(path, path.relative_to(release_dir.parent))


def build_portable_release(
    project_root: Path,
    runtime_source: Path,
    output_root: Path,
) -> tuple[Path, Path]:
    project_root = project_root.resolve()
    runtime_source = runtime_source.resolve()
    output_root = output_root.resolve()
    version = (project_root / "VERSION").read_text(encoding="utf-8").strip()
    release_dir = output_root / f"CranePlan_Portable_{version}"
    archive = output_root / f"CranePlan_Portable_{version}_Windows.zip"

    if release_dir.exists() or archive.exists():
        raise FileExistsError(
            f"Release destination already exists: {release_dir} or {archive}"
        )
    if not (runtime_source / "python.exe").is_file():
        raise FileNotFoundError(f"Portable Python runtime not found: {runtime_source}")

    required_directories = [project_root / name for name in APP_DIRECTORIES]
    required_files = [project_root / name for name in APP_FILES]
    required_files.extend(
        (
            project_root / "Запустить КранПлан.bat",
            project_root / "07_docs" / "USER_GUIDE.md",
        )
    )
    missing = [path for path in required_directories if not path.is_dir()]
    missing.extend(path for path in required_files if not path.is_file())
    if missing:
        raise FileNotFoundError(f"Required release input is missing: {missing[0]}")

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "05_src"))
    from crane_plan.pprk_assets import validate_asset_library
    issues = validate_asset_library(project_root / "05_src/crane_plan/assets/pprk")
    if issues:
        raise ValueError("Invalid PPRk asset library: " + "; ".join(
            f"{issue.asset_id}: {issue.code}: {issue.message}" for issue in issues))

    app_root = release_dir / "app"
    output_root.mkdir(parents=True, exist_ok=True)
    app_root.mkdir(parents=True)

    for directory in APP_DIRECTORIES:
        source = project_root / directory
        shutil.copytree(source, app_root / directory, ignore=_ignore_generated)
    for filename in APP_FILES:
        shutil.copy2(project_root / filename, app_root / filename)

    # Copy filters can exclude a manifest-listed path; verify the actual payload.
    packaged_issues = validate_asset_library(app_root / "05_src/crane_plan/assets/pprk")
    if packaged_issues:
        raise ValueError("Invalid packaged PPRk asset library: " + "; ".join(
            f"{issue.asset_id}: {issue.code}: {issue.message}" for issue in packaged_issues))

    shutil.copytree(runtime_source, release_dir / "runtime", ignore=_ignore_generated)
    shutil.copy2(project_root / "Запустить КранПлан.bat", release_dir / "Запустить КранПлан.bat")
    shutil.copy2(
        project_root / "07_docs" / "USER_GUIDE.md",
        release_dir / "Руководство пользователя.md",
    )
    (release_dir / "VERSION.txt").write_text(
        f"КранПлан {version}\nРасчётное ядро {version}\n",
        encoding="utf-8",
    )
    (release_dir / "ПРОЧТИТЕ_ПЕРЕД_ЗАПУСКОМ.txt").write_text(
        "КранПлан — автономная предварительная расстановка башенных кранов.\n\n"
        "1. Распакуйте ZIP целиком в отдельную папку на локальном диске.\n"
        "2. Запустите файл «Запустить КранПлан.bat».\n"
        "3. Не переносите отдельно BAT-файл, папки app или runtime.\n\n"
        "Интернет и установка Python не требуются. Итоговый ППРк является "
        "предварительным и требует проверки ответственным специалистом.\n",
        encoding="utf-8",
    )

    _write_archive(release_dir, archive)
    return release_dir, archive


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the portable CranePlan release")
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    output_root = args.output or project_root / "10_exports" / "releases"
    release_dir, archive = build_portable_release(project_root, args.runtime, output_root)
    print(release_dir)
    print(archive)


if __name__ == "__main__":
    main()
