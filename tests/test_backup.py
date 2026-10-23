"""پشتیبان‌گیری خودکار و بازگردانی."""
import pytest

from voice2excel import backup, dictionary


@pytest.fixture()
def bdir(tmp_path, monkeypatch):
    d = tmp_path / "auto-backups"
    d.mkdir()
    monkeypatch.setattr(backup, "backup_dir", lambda: d)
    return d


def test_create_list_and_restore(db, bdir):
    dictionary.add_entity(db, "رجبی", "engineer")
    made = backup.create_backup(db, "manual")
    assert made["counts"]["entities"] == 1
    # تغییر پس از پشتیبان
    dictionary.add_entity(db, "عبدی", "engineer")
    assert len(dictionary.list_entities(db, "engineer")) == 2
    res = backup.restore_backup(db, made["name"])
    names = [e["canonical"] for e in dictionary.list_entities(db, "engineer")]
    assert names == ["رجبی"]  # به وضعیت پشتیبان برگشت
    # پیش از بازگردانی، از وضعیت قبلی پشتیبان گرفته شد و قابل بازگشت است
    assert res["safety_backup"].endswith("before-restore.zip")
    backup.restore_backup(db, res["safety_backup"])
    assert len(dictionary.list_entities(db, "engineer")) == 2


def test_daily_backup_only_once_per_day(db, bdir):
    assert backup.maybe_daily_backup(db) is None  # هنوز اطلاعاتی نیست
    dictionary.add_entity(db, "رجبی", "engineer")
    assert backup.maybe_daily_backup(db)["reason"] == "auto"
    assert backup.maybe_daily_backup(db) is None  # امروز گرفته شده


def test_prune_keeps_limit(db, bdir, monkeypatch):
    monkeypatch.setattr(backup, "KEEP_AUTO", 3)
    for i in range(5):
        (bdir / f"backup-2026010{i}-000000-auto.zip").write_bytes(b"x")
    backup.prune()
    assert sorted(p.name for p in bdir.glob("*.zip")) == [f"backup-2026010{i}-000000-auto.zip" for i in (2, 3, 4)]


def test_invalid_names_rejected(db, bdir):
    with pytest.raises(backup.BackupError):
        backup.backup_path("../../voice2excel.db")
    (bdir / "backup-20260101-000000-manual.zip").write_bytes(b"not a zip")
    with pytest.raises(backup.BackupError, match="خراب"):
        backup.restore_backup(db, "backup-20260101-000000-manual.zip")
