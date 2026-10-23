"""Privacy check run before every commit (and in CI).

Refuses:
- any image, video or raw array file (by extension and by content), except reviewed
  demo-mode assets under docs/assets/demo/;
- local Windows/Unix user paths, private artifact links, e-mail addresses other than
  no-reply ones;
- every pattern listed in .privacy-patterns.local (one regular expression per line).
  That file is ignored by git: the personal strings it searches for are never published.

Usage:
    python scripts/privacy_check.py --staged      # pre-commit hook
    python scripts/privacy_check.py --all-files   # every tracked file
    python scripts/privacy_check.py --history     # the whole git history, authors included
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL_PATTERNS = ROOT / ".privacy-patterns.local"

MEDIA_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".heic", ".heif", ".raw", ".dng",
    ".mp4", ".avi", ".mov", ".mkv", ".webm", ".wmv", ".m4v", ".3gp", ".npy", ".npz", ".yuv",
}
ALLOWED_MEDIA_PREFIXES = ("docs/assets/demo/",)
MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image PNG"),
    (b"\xff\xd8\xff", "image JPEG"),
    (b"GIF87a", "image GIF"),
    (b"GIF89a", "image GIF"),
    (b"\x93NUMPY", "tableau NumPy"),
    (b"\x1aE\xdf\xa3", "vidéo Matroska/WebM"),
    (b"BM", None),  # too generic alone: only with a .bmp-like header size, see _sniff
)

GENERIC_PATTERNS = (
    (re.compile(r"\b[A-Za-z]:\\+Users\\+(?!<|%|\{|\$|Public\b|USERNAME\b|nom\b|name\b|runneradmin\b)[^\\\s\"'<>|*?]+",
                re.IGNORECASE), "chemin local Windows"),
    (re.compile(r"(?<![\w.])/(?:Users|home)/(?!<|\$|\{|runner\b)[A-Za-z0-9._-]+/"), "chemin local"),
    (re.compile(r"claude\.ai/(?:code/)?artifact/", re.IGNORECASE), "lien d'artefact privé"),
    (re.compile(r"(?<![\w.%+-])[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"),
     "adresse e-mail"),
)
ALLOWED_EMAIL_SUFFIXES = ("@users.noreply.github.com", "noreply@anthropic.com", "@example.com", "@example.org",
                          "@example.net")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    reason: str

    def __str__(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        return f"  {where}  ->  {self.reason}"


def load_local_patterns(path: Path = LOCAL_PATTERNS) -> list[tuple[re.Pattern, str]]:
    if not path.exists():
        return []
    patterns = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            patterns.append((re.compile(line), "donnée personnelle ou d'entreprise (motif local)"))
    return patterns


def _sniff(data: bytes) -> str | None:
    for magic, label in MAGIC:
        if label and data.startswith(magic):
            return label
    if data[4:8] == b"ftyp":
        return "vidéo ou image MP4/MOV/HEIC"
    if data.startswith(b"RIFF") and data[8:12] in (b"AVI ", b"WEBP"):
        return "vidéo AVI ou image WebP"
    if data.startswith(b"BM") and len(data) > 26 and int.from_bytes(data[14:18], "little") in (12, 40, 108, 124):
        return "image BMP"
    return None


def check_media(path: str, data: bytes) -> list[Finding]:
    if path.startswith(ALLOWED_MEDIA_PREFIXES):
        return []
    findings = []
    if Path(path).suffix.lower() in MEDIA_EXTENSIONS:
        findings.append(Finding(path, 0, "fichier image/vidéo interdit dans le dépôt"))
    kind = _sniff(data)
    if kind:
        findings.append(Finding(path, 0, f"contenu de type {kind} interdit dans le dépôt"))
    return findings


def check_text(path: str, text: str, patterns) -> list[Finding]:
    findings = []
    for number, line in enumerate(text.splitlines(), start=1):
        for pattern, reason in patterns:
            for match in pattern.finditer(line):
                value = match.group(0)
                if reason == "adresse e-mail" and value.lower().endswith(ALLOWED_EMAIL_SUFFIXES):
                    continue
                findings.append(Finding(path, number, reason))
    return findings


def check_file(path: str, data: bytes, patterns) -> list[Finding]:
    findings = check_media(path, data)
    if b"\x00" not in data[:8192]:
        findings += check_text(path, data.decode("utf-8", errors="replace"), patterns)
    findings += check_text(path, path, [(p, r) for p, r in patterns if r != "adresse e-mail"])
    return findings


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def staged_files() -> list[tuple[str, bytes]]:
    names = _git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR").decode("utf-8").split("\0")
    return [(name, _git("show", f":{name}")) for name in names if name]


def tracked_files() -> list[tuple[str, bytes]]:
    names = _git("ls-files", "-z").decode("utf-8").split("\0")
    return [(name, (ROOT / name).read_bytes()) for name in names if name and (ROOT / name).is_file()]


def history_findings(patterns) -> list[Finding]:
    findings: list[Finding] = []
    identities = _git("log", "--all", "--format=%ae%n%ce").decode("utf-8", errors="replace").split()
    for email in sorted(set(identities)):
        if not email.lower().endswith(ALLOWED_EMAIL_SUFFIXES):
            findings.append(Finding("(auteurs des commits)", 0, f"adresse e-mail non « noreply » : {email}"))
    log = _git("log", "--all", "-p", "--no-color", "--format=commit %H%n%B").decode("utf-8", errors="replace")
    current = "(message de commit)"
    in_diff = False
    for number, line in enumerate(log.splitlines(), start=1):
        if line.startswith("commit ") and len(line) == 47:
            current, in_diff = "(message de commit)", False
            continue
        if line.startswith("diff --git "):
            current, in_diff = line.split(" b/", 1)[-1], True
            if Path(current).suffix.lower() in MEDIA_EXTENSIONS and not current.startswith(ALLOWED_MEDIA_PREFIXES):
                findings.append(Finding(current, 0, "fichier image/vidéo présent dans l'historique"))
            continue
        if in_diff:
            if not line.startswith("+") or line.startswith("+++"):
                continue  # only what was added; removed and context lines were checked when added
            line = line[1:]
        for finding in check_text(current, line, patterns):
            findings.append(Finding(f"{finding.path} (historique, ligne {number} du journal)", 0, finding.reason))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--staged", action="store_true")
    group.add_argument("--all-files", action="store_true")
    group.add_argument("--history", action="store_true")
    args = parser.parse_args(argv)

    patterns = list(GENERIC_PATTERNS) + load_local_patterns()
    if args.history:
        findings = history_findings(patterns)
    else:
        files = staged_files() if args.staged else tracked_files()
        findings = [f for name, data in files for f in check_file(name, data, patterns)]
    if findings:
        print("Contrôle de confidentialité : refusé.")
        for finding in findings:
            print(finding)
        print("Retirez ces éléments avant de continuer (rien n'a été modifié).")
        return 1
    scope = "historique" if args.history else ("fichiers indexés" if args.staged else "fichiers suivis")
    local = "avec" if LOCAL_PATTERNS.exists() else "sans"
    print(f"Contrôle de confidentialité : OK ({scope}, {local} motifs locaux).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
