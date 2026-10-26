"""داده پایه از آموخته‌ها: فقط خیابان و اصلاح آدرس (نه نام اشخاص یا عدد بلند)؛ اصلاح خود کاربر مقدم است."""
import sqlite3
import sys
from pathlib import Path

from voice2excel import dictionary, geo, learning

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_geo  # noqa: E402


def test_learned_takes_only_streets_and_address_corrections(db, tmp_path):
    eid = dictionary.add_entity(db, "سجادیه", "street")
    dictionary.add_alias(db, eid, "سجادیع")
    dictionary.add_entity(db, "کاظمی", "engineer")
    dictionary.add_entity(db, "پروژه آسمان", "project")
    dictionary.add_entity(db, "بلوار 09151234567", "street")
    with db.tx() as c:
        c.executemany("INSERT INTO corrections(field_group, wrong, right, count, enabled) VALUES(?,?,?,?,?)", [
            ("address", "وکیلاباد", "وکیل‌آباد", 3, 1), ("name", "کازمی", "کاظمی", 5, 1),
            ("address", "خاموش", "روشن", 4, 0), ("address", "پلاک", "1234", 2, 1)])
    copy = tmp_path / "copy.db"
    src = sqlite3.connect(db.path)
    src.backup(sqlite3.connect(copy))
    streets, corr = build_geo.learned(copy)
    assert [s[0] for s in streets] == ["سجادیه"] and "سجادیع" in streets[0][1]
    assert [(w, r) for w, r, _ in corr] == [("وکیلاباد", "وکیل‌آباد")]


def test_base_corrections_apply_but_user_choice_wins(db, settings, monkeypatch):
    monkeypatch.setattr(geo, "base_corrections", lambda: (("address", "وکیلاباد", "وکیل‌آباد", 3),
                                                         ("address", "سجادیع", "سجادیه", 3)))
    settings.learn_auto_threshold = 2
    out = learning.apply_learned(db, settings, {"address": "وکیلاباد 12 سجادیع"})
    assert out["address"] == "وکیل‌آباد 12 سجادیه"
    with db.tx() as c:  # کاربر این اصلاح را خاموش کرده است
        c.execute("INSERT INTO corrections(field_group, wrong, right, count, enabled) VALUES('address','سجادیع','سجادیه',1,0)")
    assert learning.apply_learned(db, settings, {"address": "سجادیع"})["address"] == "سجادیع"
    settings.kb_base_pack = False
    assert learning.apply_learned(db, settings, {"address": "وکیلاباد"})["address"] == "وکیلاباد"
