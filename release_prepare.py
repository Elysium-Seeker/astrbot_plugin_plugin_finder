from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
METADATA_PATH = ROOT / "metadata.yaml"
MAIN_PATH = ROOT / "main.py"
README_PATH = ROOT / "README.md"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
METADATA_VERSION_RE = re.compile(r"^version:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$", re.MULTILINE)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _parse_version(text: str) -> str:
    match = METADATA_VERSION_RE.search(text)
    if not match:
        raise ValueError("metadata.yaml 中未找到 version 字段")
    return match.group(1)


def _bump_patch(version: str) -> str:
    major, minor, patch = version.split(".")
    return f"{int(major)}.{int(minor)}.{int(patch) + 1}"


def _update_metadata_version(text: str, new_version: str) -> str:
    updated, count = METADATA_VERSION_RE.subn(f"version: {new_version}", text, count=1)
    if count != 1:
        raise ValueError("更新 metadata.yaml version 失败")
    return updated


def _update_main_version(text: str, old_version: str, new_version: str) -> str:
    old_fragment = f'"{old_version}",'
    new_fragment = f'"{new_version}",'
    if old_fragment in text:
        return text.replace(old_fragment, new_fragment, 1)

    pattern = re.compile(
        r'(@register\([\s\S]*?)("[0-9]+\.[0-9]+\.[0-9]+")(?=\s*,\s*\)\s*\nclass\s+PluginFinder)',
        re.MULTILINE,
    )
    updated, count = pattern.subn(rf'\1"{new_version}"', text, count=1)
    if count != 1:
        raise ValueError("更新 main.py 注册版本失败")
    return updated


def _build_readme_bullet(new_version: str, changes: list[str]) -> str:
    summary = "；".join(changes)
    if summary.endswith("。"):
        return f"- `v{new_version}`：{summary}"
    return f"- `v{new_version}`：{summary}。"


def _update_readme_recent_updates(text: str, bullet: str) -> str:
    if bullet in text:
        return text

    marker = "## 🆕 最近更新"
    marker_pos = text.find(marker)
    if marker_pos < 0:
        return text

    line_end = text.find("\n", marker_pos)
    if line_end < 0:
        return text + "\n\n" + bullet + "\n"

    insert_pos = line_end + 1
    return text[:insert_pos] + "\n" + bullet + "\n" + text[insert_pos:]


def _ensure_changelog_header(text: str) -> str:
    if not text.strip():
        return "# Changelog\n\n所有对本项目的显著变更都会记录在此。\n\n"

    stripped = text.lstrip()
    if stripped.startswith("# Changelog"):
        return text

    return "# Changelog\n\n所有对本项目的显著变更都会记录在此。\n\n" + stripped


def _build_changelog_section(new_version: str, changes: list[str], today: str) -> str:
    lines = [f"## v{new_version} - {today}", ""]
    lines.extend(f"- {change}" for change in changes)
    lines.append("")
    return "\n".join(lines)


def _update_changelog(text: str, section: str, new_version: str) -> str:
    if re.search(rf"^##\s+v{re.escape(new_version)}\b", text, re.MULTILINE):
        return text

    first_section = re.search(r"^##\s+v[0-9]+\.[0-9]+\.[0-9]+\b", text, re.MULTILINE)
    if first_section:
        idx = first_section.start()
        return text[:idx] + section + text[idx:]

    if not text.endswith("\n"):
        text += "\n"
    return text + "\n" + section


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="准备一次 AstrBot 可识别的发布：同步版本并写入 changelog。"
    )
    parser.add_argument("--version", default="", help="指定版本号，例如 1.1.17")
    parser.add_argument(
        "--change",
        action="append",
        default=[],
        help="本次更新说明，可重复传入多个 --change",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    changes = [item.strip() for item in args.change if item and item.strip()]
    if not changes:
        raise SystemExit("请至少提供一个 --change")

    metadata_text = _read_text(METADATA_PATH)
    current_version = _parse_version(metadata_text)

    target_version = args.version.strip() if args.version else _bump_patch(current_version)
    if not VERSION_RE.fullmatch(target_version):
        raise SystemExit(f"版本号格式不合法: {target_version}")
    if target_version == current_version:
        raise SystemExit(f"目标版本与当前版本相同: {target_version}")

    _write_text(METADATA_PATH, _update_metadata_version(metadata_text, target_version))

    main_text = _read_text(MAIN_PATH)
    _write_text(MAIN_PATH, _update_main_version(main_text, current_version, target_version))

    readme_text = _read_text(README_PATH)
    bullet = _build_readme_bullet(target_version, changes)
    _write_text(README_PATH, _update_readme_recent_updates(readme_text, bullet))

    changelog_text = _read_text(CHANGELOG_PATH) if CHANGELOG_PATH.exists() else ""
    changelog_text = _ensure_changelog_header(changelog_text)
    section = _build_changelog_section(target_version, changes, date.today().isoformat())
    _write_text(CHANGELOG_PATH, _update_changelog(changelog_text, section, target_version))

    print(f"release_prepared v{target_version}")
    for change in changes:
        print(f"- {change}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
