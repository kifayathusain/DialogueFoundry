"""Retain installed runtime metadata and upstream license files in local builds."""

import argparse
import json
import shutil
import sys
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

PUBLIC_FILES = (
    "README.md",
    "COPYRIGHT.md",
    "THIRD_PARTY_NOTICES.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "SUPPORT.md",
    "CHANGELOG.md",
)


def copy_public_material(output: Path) -> bool:
    """Retain public guides/notices without importing private development records."""
    repository = Path(__file__).resolve().parent.parent
    for name in PUBLIC_FILES:
        shutil.copy2(repository / name, output / name)
    shutil.copytree(
        repository / "documentation", output / "documentation", dirs_exist_ok=True
    )
    examples = repository / "examples"
    for pattern in (
        "hello*",
        "structured/*.json",
        "audio_director/*.json",
        "audio_director/Lessons/*.json",
    ):
        for source in examples.glob(pattern):
            if source.is_file():
                target = output / source.relative_to(repository)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    for name in ("catalog.py", "piper_english.json"):
        source = repository / "ttsapp" / "models" / name
        target = output / "ttsapp" / "models" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    application_license = repository / "LICENSE"
    if application_license.is_file():
        shutil.copy2(application_license, output / "LICENSE")
        return True
    return False


def write_notices(output: Path, profile: str) -> None:
    """Retain dependency evidence without claiming distribution clearance."""
    pending = ["edge-tts", "pyinstaller"]
    if profile == "full":
        pending.extend(("kokoro-onnx", "piper-tts"))
    records = []
    seen = set()
    while pending:
        name = canonicalize_name(pending.pop())
        if name in seen:
            continue
        seen.add(name)
        distribution = metadata.distribution(name)
        destination = output / "licenses" / name
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "METADATA.txt").write_text(
            distribution.read_text("METADATA") or "", encoding="utf-8"
        )
        copied = []
        for asset in distribution.files or ():
            if ".." in asset.parts:
                continue
            if not any(
                word in asset.name.lower()
                for word in ("license", "copying", "notice", "authors")
            ):
                continue
            source = Path(distribution.locate_file(asset))
            if source.is_file():
                target = destination / str(asset)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                copied.append(str(asset))
        records.append(
            {
                "name": distribution.metadata["Name"],
                "version": distribution.version,
                "license_expression": distribution.metadata.get("License-Expression"),
                "license": distribution.metadata.get("License"),
                "license_classifiers": [
                    value
                    for value in distribution.metadata.get_all("Classifier", [])
                    if value.startswith("License ::")
                ],
                "project_urls": distribution.metadata.get_all("Project-URL", []),
                "license_files": copied,
            }
        )
        for dependency in distribution.requires or ():
            requirement = Requirement(dependency)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise FileNotFoundError("The build runtime must provide Python LICENSE.txt.")
    shutil.copy2(python_license, output / "licenses" / "PYTHON-LICENSE.txt")
    has_application_license = copy_public_material(output)
    (output / "dependency-inventory.json").write_text(
        json.dumps(sorted(records, key=lambda item: item["name"]), indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "THIRD_PARTY_NOTICES.txt").write_text(
        "DialogueFoundry local QA build; NOT cleared for public distribution.\n"
        "See THIRD_PARTY_NOTICES.md, documentation/LICENSING.md, licenses/ and\n"
        "dependency-inventory.json. A metadata inventory is not a complete\n"
        "native-binary audit or corresponding-source distribution.\n"
        + (
            "Application LICENSE copied; its presence is not distribution clearance.\n"
            if has_application_license
            else "No application LICENSE present; restore it before distribution.\n"
        )
        + "Full profiles include GPL Piper, phonemizer and eSpeak components.\n"
        "Resolve missing native notices, permissions and complete matching\n"
        "corresponding source/build materials before binary distribution.\n"
        "Model weights have separate, sometimes restrictive or unresolved terms.\n",
        encoding="utf-8",
    )


def main() -> None:
    """Generate notices alongside a completed PyInstaller folder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--profile", choices=("full", "edge"), required=True)
    args = parser.parse_args()
    write_notices(args.output, args.profile)


if __name__ == "__main__":
    main()
