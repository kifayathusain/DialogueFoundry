"""Package notices preserve license evidence without implying release approval."""

import json
from email.message import Message
from pathlib import Path

import pytest

from scripts import package_notices


class InstalledDistribution:
    """Small installed distribution fixture with real notice assets."""

    version = "2.0"

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.metadata = Message()
        self.metadata["Name"] = directory.name
        self.metadata["License"] = "GPL-3.0-or-later"
        self.metadata["Classifier"] = "License :: OSI Approved :: GNU GPL"
        self.files = [Path("COPYING"), Path("AUTHORS"), Path("../private.txt")]
        self.requires = ['optional-runtime; extra == "gpu"']
        for name in ("COPYING", "AUTHORS"):
            (directory / name).write_text(f"Upstream {name}", encoding="utf-8")

    def read_text(self, filename: str) -> str:
        """Return the installed metadata representation."""
        return str(self.metadata)

    def locate_file(self, asset: Path) -> Path:
        """Locate one fixture asset."""
        return self.directory / asset


def prepare_runtime(monkeypatch, tmp_path: Path) -> None:
    """Provide metadata and the mandatory Python license without installed tools."""
    runtime = tmp_path / "python"
    runtime.mkdir()
    (runtime / "LICENSE.txt").write_text("Python license", encoding="utf-8")
    monkeypatch.setattr(package_notices.sys, "base_prefix", str(runtime))

    def distribution(name: str) -> InstalledDistribution:
        directory = tmp_path / name
        directory.mkdir(exist_ok=True)
        return InstalledDistribution(directory)

    monkeypatch.setattr(package_notices.metadata, "distribution", distribution)


@pytest.mark.parametrize("profile", ["edge", "full"])
@pytest.mark.parametrize("licensed", [False, True])
def test_notice_inventory_retains_texts_and_distribution_warning(
    monkeypatch, tmp_path: Path, profile: str, licensed: bool
) -> None:
    prepare_runtime(monkeypatch, tmp_path)
    output = tmp_path / "package"
    output.mkdir()
    monkeypatch.setattr(package_notices, "copy_public_material", lambda _: licensed)

    package_notices.write_notices(output, profile)

    inventory = json.loads((output / "dependency-inventory.json").read_text())
    expected = {"edge-tts", "pyinstaller"}
    if profile == "full":
        expected.update({"piper-tts", "kokoro-onnx"})
    assert {record["name"] for record in inventory} == expected
    for record in inventory:
        assert record["license"] == "GPL-3.0-or-later"
        assert record["license_classifiers"] == ["License :: OSI Approved :: GNU GPL"]
        assert record["license_files"] == ["COPYING", "AUTHORS"]
        assert (output / "licenses" / record["name"] / "COPYING").read_text() == (
            "Upstream COPYING"
        )
    warning = (output / "THIRD_PARTY_NOTICES.txt").read_text()
    assert "NOT cleared for public distribution" in warning
    if licensed:
        assert "Application LICENSE copied" in warning
    else:
        assert "No application LICENSE present" in warning
    assert "corresponding source" in warning


def test_missing_python_license_remains_an_error(monkeypatch, tmp_path: Path) -> None:
    prepare_runtime(monkeypatch, tmp_path)
    (tmp_path / "python" / "LICENSE.txt").unlink()
    output = tmp_path / "package"
    output.mkdir()

    with pytest.raises(FileNotFoundError, match="Python LICENSE.txt"):
        package_notices.write_notices(output, "edge")
    assert not (output / "THIRD_PARTY_NOTICES.txt").exists()


@pytest.mark.parametrize("licensed", [False, True])
def test_public_material_excludes_internal_records(
    monkeypatch, tmp_path: Path, licensed: bool
) -> None:
    repository = tmp_path / "repository"
    (repository / "scripts").mkdir(parents=True)
    (repository / "documentation").mkdir()
    (repository / "examples").mkdir()
    (repository / "examples" / "hello.txt").write_text("Public example")
    (repository / "examples" / "private.md").write_text("Private notes")
    (repository / "ttsapp" / "models").mkdir(parents=True)
    for name in ("catalog.py", "piper_english.json"):
        (repository / "ttsapp" / "models" / name).write_text("Public reference")
    (repository / "docs").mkdir()
    (repository / "docs" / "private.txt").write_text("Private record")
    (repository / "AGENTS.md").write_text("Private instructions")
    for name in package_notices.PUBLIC_FILES:
        (repository / name).write_text(name, encoding="utf-8")
    (repository / "documentation" / "LICENSING.md").write_text("Public audit")
    if licensed:
        (repository / "LICENSE").write_text("Approved license")
    monkeypatch.setattr(
        package_notices, "__file__", str(repository / "scripts" / "package_notices.py")
    )
    output = tmp_path / "package"
    output.mkdir()

    assert package_notices.copy_public_material(output) is licensed
    assert (output / "THIRD_PARTY_NOTICES.md").is_file()
    assert (output / "COPYRIGHT.md").read_text() == "COPYRIGHT.md"
    assert (output / "documentation" / "LICENSING.md").read_text() == "Public audit"
    assert (output / "LICENSE").exists() is licensed
    if licensed:
        assert (output / "LICENSE").read_bytes() == b"Approved license"
    assert not (output / "docs").exists()
    assert not (output / "AGENTS.md").exists()
    assert (output / "examples" / "hello.txt").read_text() == "Public example"
    assert not (output / "examples" / "private.md").exists()
