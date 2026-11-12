"""واژه‌نامه پایه نام‌ها (voice2excel/assets/geo.dat، از scripts/build_names.py): املای هم‌آوا یکسان می‌شود، املای درست دست نمی‌خورد."""
from voice2excel import geo
from voice2excel.lexicon import Lexicon


def _lex():
    return Lexicon.build([], base=geo.base_streets(), base_names=geo.base_names())


def test_base_lists_size():
    surnames, first = geo.base_names()
    assert len(surnames) >= 5000 and len(first) >= 2000


def test_homophones_unified_to_common_spelling():
    lex = _lex()
    for heard, right in [("کازمی", "کاظمی"), ("قاصمی", "قاسمی"), ("تاهری", "طاهری"), ("سادقی", "صادقی"), ("علی کازمی", "علی کاظمی")]:
        assert lex.canonical_engineer(heard) == right, heard


def test_correct_spellings_untouched():
    lex = _lex()
    for name in ["حسینی", "طاهری", "اسلامی", "سمیعی", "کاظمی", "علی کاظمی"]:
        assert lex.canonical_engineer(name) is None, name


def test_haji_prefixed_names_not_reduced_to_suffix():
    # «حاجی پور» با فاصله کلید «پور» می‌گرفت و هر «…پور» را عوض می‌کرد؛ در فهرست با نیم‌فاصله است
    surnames, _ = geo.base_names()
    assert not any(n.startswith(("حاجی ", "حاج ")) for n in surnames)
    assert _lex().canonical_engineer("پور") is None
