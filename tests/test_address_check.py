"""بررسی آدرس با نقشه: فقط «دور + هم‌آوای نزدیک» هشدار می‌دهد؛ آدرس درست و تک‌خیابانی دست نمی‌خورد."""
import difflib

import pytest

from voice2excel import address_check as ac
from voice2excel.validator import validate


@pytest.fixture(scope="module")
def case():
    """از خود داده نقشه: خیابان اصلی، فرعیِ نزدیک واقعی، و خیابان واقعیِ هم‌آوا ولی دور."""
    keys, names, _, _ = ac._index()
    for main in keys[::7]:
        d = ac._distances_from(main)
        for side in [k for k in keys if k != main and d[k] <= 0.3]:
            far = [k for k in keys if k not in (main, side) and d[k] > 3
                   and difflib.SequenceMatcher(None, k, side).ratio() >= 0.8]
            if far:
                return names[main], names[side], names[far[0]]
    pytest.skip("داده نقشه در دسترس نیست")


def test_misheard_side_street_flagged_with_nearby_suggestion(case):
    main, side, far = case
    r = ac.check(f"{main} 12، {far} 5، پلاک 3")
    assert len(r) == 1 and r[0]["suggestion"] == side and r[0]["heard"] == far and r[0]["km"] > 2


@pytest.mark.parametrize("make", [
    lambda m, s, f: f"{m} 12، {s} 5، پلاک 3",   # آدرس درست
    lambda m, s, f: f"{m} 12، پلاک 3",          # فقط یک خیابان
    lambda m, s, f: "",
])
def test_no_flag_for_correct_or_single_street(case, make):
    assert ac.check(make(*case)) == []


def test_validator_suggests_fixed_address_and_respects_user(db, settings, case):
    main, side, far = case
    heard = f"{main} 12، {far} 5، پلاک 3"
    v = validate(db, {"address": heard}, {}, settings)
    fc = v.fields["address"]
    assert fc.status == "review" and fc.suggestions[0] == f"{main} 12، {side} 5، پلاک 3"
    assert any("کیلومتر" in r for r in fc.reasons)
    # آدرسی که کاربر اصلاح یا تأیید کرده، دوباره علامت نمی‌خورد؛ و با خاموش بودن داده پایه هم نه
    assert not validate(db, {"address": heard}, {}, settings, edited={"address"}).fields["address"].suggestions
    settings.kb_base_pack = False
    assert not any("کیلومتر" in r for r in validate(db, {"address": heard}, {}, settings).fields["address"].reasons)


def test_guess_goes_in_row_original_is_one_click_and_not_learned(db, settings, case, monkeypatch):
    """حدس محتمل‌تر در ردیف؛ برگرداندن به آنچه شنیده شد با یک کلیک و بدون «یادگیری» اصلاح همیشگی."""
    from fastapi.testclient import TestClient

    from voice2excel import pipeline, server
    main, side, far = case
    text = f"مهندس کاظمی شماره 09151112233 آدرس {main} 12، {far} 5"
    _, clauses, out = pipeline.build_records(db, settings, text, "1405/08/04")
    rec = out[0]
    heard = rec["extracted"]["meta"]["map_fix"]["from"]
    assert far in heard and rec["values"]["address"] == heard.replace(far, side, 1)
    fc = rec["validation"]["fields"]["address"]
    assert rec["validation"]["status"] != "ready" and fc["suggestions"][0] == heard and "کیلومتر" in fc["reasons"][0]

    batch = db.create_batch("آزمون", "1405/08/04")
    aid = db.add_audio(batch, "a.wav", "a.wav", "x" * 64, 1, "1405/08/04", "user")
    db.save_results(aid, {"raw_text": text, "normalized_text": text, "processed_text": text, "segments": [],
                          "words": [], "clauses": clauses, "language": "fa", "language_prob": 1, "avg_logprob": 0,
                          "model": "t"}, out)
    rid = db.q("SELECT id FROM records WHERE audio_id=?", (aid,))[0]["id"]
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    with TestClient(server.app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8765",
                    headers=server.auth_headers()) as c:
        r = c.post(f"/api/records/{rid}/accept", json={"field": "address", "value": heard}).json()
    assert r["values"]["address"] == heard and r["validation"]["fields"]["address"]["status"] != "review"
    assert db.q("SELECT * FROM corrections") == []  # «حسنی ← حسینیه» یاد گرفته نشد
