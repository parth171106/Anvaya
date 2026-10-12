"""Create a source-only deployment archive; never include local logs, keys or secrets."""
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = ("backend/app", "backend/Dockerfile", "backend/requirements.lock", "backend/pyproject.toml",
           "generator", "frontend", "deploy/Caddyfile", "docker-compose.deploy.yml", ".dockerignore")
EXCLUDE = {"node_modules", "dist", "data", "secrets", ".git", ".npm-cache", "__pycache__", ".pytest_cache",
           ".ruff_cache", "test-results", "playwright-report"}


def package():
    destination = ROOT / "data" / "anvaya-deploy.tar.gz"
    destination.parent.mkdir(exist_ok=True)
    count = 0
    with tarfile.open(destination, "w:gz") as archive:
        for name in INCLUDE:
            base = ROOT / name
            paths = base.rglob("*") if base.is_dir() else [base]
            for path in paths:
                relative = path.relative_to(ROOT)
                if (path.is_symlink() or not path.is_file() or EXCLUDE.intersection(relative.parts)
                        or path.name.startswith(".env") or path.suffix in (".pem", ".key", ".pyc")):
                    continue
                if not path.resolve().is_relative_to(ROOT):
                    raise ValueError(f"Outside source tree: {relative}")
                archive.add(path, arcname=relative.as_posix(), recursive=False)
                count += 1
    print(f"Packaged {count} source files ({destination.stat().st_size} bytes): {destination}")


if __name__ == "__main__":
    package()
