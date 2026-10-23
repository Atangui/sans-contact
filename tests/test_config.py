import json
import os
from pathlib import Path

import pytest

from sanscontact.config import consent
from sanscontact.config import settings as store
from sanscontact.config.paths import UnsafeStorageError, check_storage_location, data_dir
from sanscontact.config.settings import Settings
from sanscontact.config.storage import delete_all_data, stored_items


def test_defaults_are_conservative():
    s = Settings()
    assert (s.frame_width, s.frame_height) == (640, 480)
    assert s.num_hands == 1 and s.pause_timeout_s == 30.0
    assert s.camera_name is None  # explicit choice, never guessed among several


def test_invalid_values_are_brought_back_into_range():
    s = Settings(frame_width=99999, num_hands=7, hand="third", one_euro_beta=-1, active_zone=[0.9, 0.9, 0.1, 0.92],
                 hotkey=" ", pause_timeout_s="nope").validated()
    assert s.frame_width == 1920 and s.num_hands == 2 and s.hand == "any" and s.one_euro_beta == 0.0
    assert s.active_zone == Settings().active_zone  # too thin after sorting: default
    assert s.hotkey == Settings().hotkey and s.pause_timeout_s == 30.0


def test_round_trip_and_unknown_keys(tmp_path):
    s = Settings(camera_name="Cam A", active_zone=[0.1, 0.1, 0.9, 0.9])
    store.save(tmp_path, s)
    raw = json.loads((tmp_path / store.SETTINGS_FILE).read_text(encoding="utf-8"))
    raw["unknown"] = 1
    (tmp_path / store.SETTINGS_FILE).write_text(json.dumps(raw), encoding="utf-8")
    assert store.load(tmp_path) == s


def test_corrupted_or_missing_file_gives_defaults(tmp_path):
    assert store.load(tmp_path) == Settings()
    (tmp_path / store.SETTINGS_FILE).write_text("{not json", encoding="utf-8")
    assert store.load(tmp_path) == Settings()


def test_example_config_lists_every_setting_with_valid_values(tmp_path):
    from dataclasses import asdict, fields

    example = Path(__file__).resolve().parents[1] / "config.example.json"
    raw = json.loads(example.read_text(encoding="utf-8"))
    assert set(raw) == {f.name for f in fields(Settings)}
    (tmp_path / store.SETTINGS_FILE).write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    loaded = asdict(store.load(tmp_path))
    assert {k: v for k, v in loaded.items() if k != "camera_name"} == {k: v for k, v in raw.items()
                                                                       if k != "camera_name"}


def test_hysteresis_band_is_always_kept():
    s = Settings(pinch_press=0.30, pinch_release=0.31).validated()
    assert s.pinch_release - s.pinch_press >= 0.05


def test_settings_hold_only_numbers_and_names(tmp_path):
    store.save(tmp_path, Settings())
    text = (tmp_path / store.SETTINGS_FILE).read_text(encoding="utf-8")
    for forbidden in ("image", "frame_data", "history", "position"):
        assert forbidden not in text


def test_data_dir_is_under_localappdata():
    path = data_dir()
    assert path.parent == Path(os.environ["LOCALAPPDATA"]) and path.name == "SansContact"


@pytest.mark.parametrize("parts", [("C:\\", "Users", "x", "OneDrive - Contoso", "SansContact"),
                                   ("D:\\", "Dropbox", "SansContact")])
def test_cloud_folders_are_refused(parts):
    with pytest.raises(UnsafeStorageError):
        check_storage_location(Path(*parts))


def test_documents_and_desktop_are_refused():
    from sanscontact.config.paths import _known_folders

    for folder in _known_folders():
        with pytest.raises(UnsafeStorageError):
            check_storage_location(folder / "SansContact")


def test_consent_stores_only_a_version(tmp_path):
    assert not consent.is_accepted(tmp_path)
    consent.accept(tmp_path)
    assert consent.is_accepted(tmp_path)
    assert json.loads((tmp_path / consent.CONSENT_FILE).read_text()) == {"version": consent.CONSENT_VERSION}
    (tmp_path / consent.CONSENT_FILE).write_text(json.dumps({"version": 0}))
    assert not consent.is_accepted(tmp_path)


def test_delete_all_data(tmp_path):
    folder = tmp_path / "SansContact"
    store.save(folder, Settings())
    consent.accept(folder)
    assert stored_items(folder) == ["consent.json", "settings.json"]
    assert delete_all_data(folder) is True
    assert not folder.exists() and stored_items(folder) == []
    assert delete_all_data(folder) is False


def test_delete_refuses_an_unexpected_folder(tmp_path):
    other = tmp_path / "Documents"
    other.mkdir()
    with pytest.raises(ValueError):
        delete_all_data(other)
    assert other.exists()
