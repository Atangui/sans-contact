"""The pre-commit check itself. Personal-looking values are built at run time, so this
file never contains them literally."""

import importlib.util
import re
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "privacy_check.py"
spec = importlib.util.spec_from_file_location("privacy_check", SCRIPT)
pc = importlib.util.module_from_spec(spec)
sys.modules["privacy_check"] = pc
spec.loader.exec_module(pc)

PATTERNS = list(pc.GENERIC_PATTERNS)
AT = "@"


def reasons(path, text, patterns=PATTERNS):
    return [f.reason for f in pc.check_file(path, text.encode("utf-8"), patterns)]


def test_media_files_are_refused_by_extension_and_content():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    assert pc.check_file("frame.png", png, PATTERNS)
    assert pc.check_file("data/notes.txt", png, PATTERNS)  # renamed image: caught by content
    assert pc.check_file("capture.npy", b"\x93NUMPY" + b"\x00" * 10, PATTERNS)
    assert pc.check_file("clip.bin", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 8, PATTERNS)
    assert pc.check_file("docs/assets/demo/studio.png", png, PATTERNS) == []  # reviewed demo assets only


def test_local_paths_and_private_links_are_refused():
    user_path = "C:" + "\\Users\\" + "alex.dupont\\Projects"
    assert "chemin local Windows" in reasons("a.md", f"see {user_path}")
    assert reasons("a.md", "stored in %LOCALAPPDATA%\\SansContact") == []
    assert reasons("a.md", "C:\\Users\\<nom>\\AppData") == []
    assert "chemin local" in reasons("a.md", "/home/" + "alex/code")
    assert "lien d'artefact privé" in reasons("a.md", "https://claude." + "ai/artifact/abc")


def test_emails_except_noreply():
    assert "adresse e-mail" in reasons("a.md", "write to alex" + AT + "contoso.com")
    assert reasons("a.md", "123+alex" + AT + "users.noreply.github.com") == []
    assert reasons("a.md", "alex.martin" + AT + "example.com") == []


def test_local_patterns(tmp_path):
    local = tmp_path / ".privacy-patterns.local"
    local.write_text("# comment\n\\bACME\\b\n(?i)jdupont\n", encoding="utf-8")
    patterns = PATTERNS + pc.load_local_patterns(local)
    assert reasons("a.md", "Projet ACME interne", patterns)
    assert reasons("JDupont-notes.md", "rien", patterns)  # file names are checked too
    assert reasons("a.md", "acmeology", patterns) == []
    assert pc.load_local_patterns(tmp_path / "missing") == []


def test_clean_text_passes():
    assert reasons("src/x.py", "def f():\n    return 1\n") == []
    decorators = [AT + "pytest.mark.parametrize('a', [1])", "+" + AT + "pytest.fixture"]
    assert reasons("tests/x.py", "\n".join(decorators)) == []


def test_whole_history_is_clean():
    assert pc.main(["--history"]) == 0


def test_this_repository_has_no_finding():
    assert pc.main(["--all-files"]) == 0


def test_the_script_does_not_flag_itself():
    text = SCRIPT.read_text(encoding="utf-8")
    assert pc.check_text("scripts/privacy_check.py", text, PATTERNS) == []
    assert re.search(r"Contrôle", text)
