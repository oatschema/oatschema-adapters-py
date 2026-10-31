# SPDX-FileCopyrightText: 2026 The OATS Authors
# SPDX-License-Identifier: Apache-2.0

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from email.parser import Parser
from importlib.metadata import packages_distributions
from pathlib import Path

import pytest

import oatschema_adapters

PROJECT = Path(__file__).resolve().parent.parent
PACKAGE = PROJECT / "src" / "oatschema_adapters"
VERSION = oatschema_adapters.__version__
AGENT_FILES = ("CLAUDE.md", "CLAUDE.local.md", ".claude/", ".claude")


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _declared() -> set[str]:
    with open(PROJECT / "pyproject.toml", "rb") as f:
        dependencies = tomllib.load(f)["project"]["dependencies"]
    return {_canonical(re.split(r"[\s<>=!~;\[]", dependency, maxsplit=1)[0]) for dependency in dependencies}


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def package_files() -> set[str]:
    return {
        f"oatschema_adapters/{path.relative_to(PACKAGE).as_posix()}"
        for path in PACKAGE.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


def test_every_import_is_a_declared_dependency() -> None:
    declared = _declared()
    distributions = packages_distributions()
    undeclared = {}
    for path in PACKAGE.rglob("*.py"):
        for name in _imports(path):
            if name in sys.stdlib_module_names or name == "oatschema_adapters":
                continue
            providers = {_canonical(d) for d in distributions.get(name, [])}
            if not providers & declared:
                undeclared[f"{path.relative_to(PROJECT)}: {name}"] = sorted(providers)
    assert not undeclared


def test_dependencies() -> None:
    with open(PROJECT / "pyproject.toml", "rb") as f:
        project = tomllib.load(f)["project"]
    assert "oatschema[validate]>=0.8.0.2,<0.9" in project["dependencies"]
    assert {_canonical(name) for name in _declared()} == {"oatschema", "srt", "webvtt-py"}


@pytest.fixture(scope="module")
def dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("building needs uv")
    out = tmp_path_factory.mktemp("dist")
    subprocess.run([uv, "build", "--quiet", "--out-dir", str(out), str(PROJECT)], check=True)
    return out


def test_wheel_contains_exactly_the_package(dist: Path) -> None:
    (wheel,) = dist.glob("*.whl")
    assert wheel.name == f"oatschema_adapters-{VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(wheel) as archive:
        all_names = archive.namelist()
    names = {name for name in all_names if not name.startswith("oatschema_adapters-")}
    assert names == package_files()
    dist_info = f"oatschema_adapters-{VERSION}.dist-info"
    assert {f"{dist_info}/licenses/LICENSE", f"{dist_info}/licenses/AUTHORS"} <= set(all_names)
    assert "oatschema_adapters/py.typed" in names
    assert not any(part in name for name in all_names for part in AGENT_FILES)


def test_wheel_metadata(dist: Path) -> None:
    (wheel,) = dist.glob("*.whl")
    with zipfile.ZipFile(wheel) as archive:
        metadata = Parser().parsestr(archive.read(f"oatschema_adapters-{VERSION}.dist-info/METADATA").decode())
    assert metadata["Name"] == "oatschema-adapters"
    assert metadata["Version"] == VERSION
    assert metadata["Requires-Python"] == ">=3.11"
    assert metadata["License-Expression"] == "Apache-2.0"
    assert set(metadata.get_all("License-File") or []) == {"LICENSE", "AUTHORS"}
    assert metadata["Author-email"] == "OATS maintainers <maintainers@oatschema.org>"
    assert not any(classifier.startswith("License ::") for classifier in metadata.get_all("Classifier") or [])
    assert "Homepage, https://oatschema.org" in (metadata.get_all("Project-URL") or [])
    requirements = {re.sub(r"\s+", "", r) for r in metadata.get_all("Requires-Dist") or []}
    assert requirements == {"oatschema[validate]<0.9,>=0.8.0.2", "srt>=3.5.3", "webvtt-py>=0.5.1"}
    assert "dorsal" not in str(metadata).lower()


def test_sdist_can_run_the_tests_and_has_no_agent_files(dist: Path) -> None:
    (sdist,) = dist.glob("*.tar.gz")
    root = f"oatschema_adapters-{VERSION}"
    with tarfile.open(sdist) as archive:
        names = {name.removeprefix(f"{root}/") for name in archive.getnames()}
    assert {"pyproject.toml", "README.md", "CHANGELOG.md", "LICENSE", "AUTHORS"} <= names
    assert {path.relative_to(PROJECT).as_posix() for path in (PROJECT / "tests").rglob("*.py")} <= names
    assert "tests/data/expected/index.json" in names
    assert {f"src/{name}" for name in package_files()} <= names
    assert not any(name.startswith(("venv/", ".venv/", ".github/")) for name in names)
    assert not any(part in name.split("/") or name.startswith(part) for name in names for part in AGENT_FILES)


def test_a_clean_install_runs_every_adapter_with_validation(dist: Path, tmp_path: Path) -> None:
    uv = shutil.which("uv")
    assert uv is not None
    (wheel,) = dist.glob("*.whl")
    venv = tmp_path / "venv"
    env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    subprocess.run([uv, "venv", "--quiet", "--python", sys.executable, str(venv)], check=True, env=env)
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run([uv, "pip", "install", "--quiet", "--python", str(python), str(wheel)], check=True, env=env)
    result = subprocess.run(
        [str(python), "-I", str(PROJECT / "scripts" / "smoke.py")],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count(": ok") == 10
    listing = subprocess.run(
        [uv, "pip", "list", "--python", str(python), "--format", "json"],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout
    installed = {_canonical(entry["name"]) for entry in json.loads(listing)}
    assert installed == {"oatschema-adapters", "oatschema", "jsonschema-rs", "srt", "webvtt-py"}
