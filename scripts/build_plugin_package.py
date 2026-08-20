"""SW-01 D5: pacote de release determinístico do plugin kdr-x.

Gera ``<out>/kdr-x-plugin-<version>.zip`` (bytes idênticos entre builds —
acceptance 4: uninstall/reinstall offline reproduz o mesmo hash) e
``<out>/SHA256SUMS`` com os hashes de todos os artefatos gerados.

Determinismo do zip por construção:

- entries ordenadas pelo arcname (caminho relativo à raiz do plugin,
  separador POSIX);
- ``ZipInfo.date_time`` fixo no zip epoch (1980-01-01) — sem timestamp de
  build dentro do artefato;
- ``external_attr`` fixo (0644) — sem vazamento do umask da máquina;
- ``__pycache__``/``*.pyc`` excluídos (artefatos de runtime, não de release).

Sem ``--no-wheel``, também roda ``pip wheel . --no-deps -w <out>`` e registra
o hash do wheel em ``SHA256SUMS``. A reprodutibilidade bit-a-bit do wheel
**não** é assertada: o setuptools carimba os entries do zip interno com o
timestamp do build (e o RECORD é regravado a cada geração), então dois builds
diferem em bytes embora o conteúdo seja equivalente. O artefato cuja
reprodutibilidade é garantida — e testada — é o zip do plugin.

Stdlib only; zero dependências novas (constraint SW-01).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = REPO_ROOT / "plugins" / "kdr-x"
DEFAULT_OUT = REPO_ROOT / "dist"

ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
FIXED_EXTERNAL_ATTR = 0o644 << 16  # permissões Unix fixas no header central


def plugin_version() -> str:
    """Versão do release, lida do manifesto do plugin.

    A paridade ``plugin.json == kdrx.__version__ == pyproject.toml`` é
    travada por teste (SW-01 D5), então qualquer uma das três serviria; o
    manifesto é lido via stdlib ``json`` (sem parser TOML, py3.10 OK).
    """
    manifest = json.loads(
        (PLUGIN_DIR / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    return str(manifest["version"])


def iter_plugin_files() -> list[Path]:
    """Arquivos do plugin em ordem determinística, sem artefatos de runtime."""
    entries = []
    for path in PLUGIN_DIR.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(PLUGIN_DIR)
        if "__pycache__" in rel.parts or rel.suffix == ".pyc":
            continue
        entries.append(rel)
    return sorted(entries, key=lambda r: r.as_posix())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_plugin_zip(version: str, out_dir: Path) -> Path:
    """Zip determinístico do plugin; arcnames relativos à raiz do plugin."""
    zip_path = out_dir / f"kdr-x-plugin-{version}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in iter_plugin_files():
            info = zipfile.ZipInfo(rel.as_posix(), date_time=ZIP_EPOCH)
            # create_system default é platform-dependent (0 no win32, 3 no
            # POSIX) e vazaria o OS do build para o header — fixo em 0.
            info.create_system = 0
            info.external_attr = FIXED_EXTERNAL_ATTR
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, (PLUGIN_DIR / rel).read_bytes())
    return zip_path


def build_wheel(version: str, out_dir: Path) -> Path:
    """Wheel pure-Python via pip (setuptools já é o build backend do repo)."""
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", str(out_dir)],
        cwd=REPO_ROOT,
        check=True,
    )
    wheels = sorted(out_dir.glob(f"kdrx-{version}-*.whl"))
    if not wheels:
        raise RuntimeError(f"pip wheel terminou sem gerar kdrx-{version}-*.whl")
    return wheels[-1]


def write_sha256sums(artifacts: list[Path], out_dir: Path) -> Path:
    """``SHA256SUMS`` no formato coreutils: ``<hash>  <nome-do-arquivo>``."""
    sums_path = out_dir / "SHA256SUMS"
    lines = [f"{sha256(artifact)}  {artifact.name}" for artifact in artifacts]
    sums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sums_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="pacote de release determinístico do plugin kdr-x (SW-01 D5)"
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT,
        help="diretório de saída dos artefatos (default: dist/)",
    )
    parser.add_argument(
        "--no-wheel",
        action="store_true",
        help="pula o build do wheel (empacota só o zip do plugin)",
    )
    args = parser.parse_args(argv)

    version = plugin_version()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    artifacts = [build_plugin_zip(version, args.out_dir)]
    if not args.no_wheel:
        artifacts.append(build_wheel(version, args.out_dir))
    sums_path = write_sha256sums(artifacts, args.out_dir)
    for artifact in artifacts:
        print(f"{sha256(artifact)}  {artifact.name}")
    print(f"SHA256SUMS: {sums_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
