"""بسته به‌روزرسانی سبک: اعتبارسنجی و آماده‌سازی."""
import json
import zipfile

import pytest

from voice2excel import __version__, updater


def _bump(v: str, step: int = 1) -> str:
    parts = [int(x) for x in v.split(".")]
    parts[-1] += step
    return ".".join(map(str, parts))


@pytest.fixture()
def env(tmp_path, monkeypatch):
    app_root = tmp_path / "app"
    app_root.mkdir()
    (app_root / "runtime.json").write_text(json.dumps({"runtime_id": "rt-1"}), encoding="utf-8")
    monkeypatch.setattr(updater, "RUNTIME_FILE", app_root / "runtime.json")
    monkeypatch.setattr(updater, "STAGE_DIR", tmp_path / "update-staged")
    src = tmp_path / "src" / "voice2excel"
    (src / "web").mkdir(parents=True)
    (src / "__init__.py").write_text('__version__ = "x"\n', encoding="utf-8")
    (src / "web" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return tmp_path, src


def test_valid_update_is_staged(env):
    tmp, src = env
    z = tmp / "u.zip"
    updater.build_update_zip(src, z, "rt-1", _bump(__version__), notes="آزمون")
    res = updater.stage_update(z)
    assert res["version"] == _bump(__version__) and res["files"] == 2
    assert (tmp / "update-staged" / "voice2excel" / "web" / "app.js").exists()
    assert updater.staged_info()["notes"] == "آزمون"
    updater.cancel_staged()
    assert updater.staged_info() is None


def test_not_newer_rejected(env):
    tmp, src = env
    z = tmp / "u.zip"
    updater.build_update_zip(src, z, "rt-1", __version__)
    with pytest.raises(updater.UpdateError, match="جدیدتر"):
        updater.inspect_update(z)


def test_runtime_mismatch_needs_full_package(env):
    tmp, src = env
    z = tmp / "u.zip"
    updater.build_update_zip(src, z, "rt-OTHER", _bump(__version__))
    with pytest.raises(updater.UpdateError, match="بسته کامل"):
        updater.inspect_update(z)


def test_dev_mode_without_runtime_file(env, monkeypatch):
    tmp, src = env
    monkeypatch.setattr(updater, "RUNTIME_FILE", tmp / "missing.json")
    z = tmp / "u.zip"
    updater.build_update_zip(src, z, "rt-1", _bump(__version__))
    with pytest.raises(updater.UpdateError, match="قابل‌حمل"):
        updater.inspect_update(z)


def _write_zip(path, manifest, members):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest))
        for name, data in members.items():
            z.writestr(name, data)


def test_path_traversal_rejected(env):
    tmp, _ = env
    z = tmp / "evil.zip"
    m = {"app": "voice2excel", "type": "update", "version": _bump(__version__), "runtime_id": "rt-1",
         "files": {"../../evil.py": "x"}}
    _write_zip(z, m, {"../../evil.py": b"print('x')"})
    with pytest.raises(updater.UpdateError, match="مسیر نامعتبر"):
        updater.inspect_update(z)
    assert not (tmp.parent / "evil.py").exists()


def test_tampered_file_and_unlisted_file_rejected(env):
    tmp, src = env
    good = tmp / "good.zip"
    m = updater.build_update_zip(src, good, "rt-1", _bump(__version__))
    bad = tmp / "bad.zip"
    _write_zip(bad, m, {"voice2excel/__init__.py": b"changed", "voice2excel/web/app.js": b"console.log(1)"})
    with pytest.raises(updater.UpdateError, match="هش"):
        updater.inspect_update(bad)
    extra = tmp / "extra.zip"
    _write_zip(extra, m, {"voice2excel/__init__.py": (src / "__init__.py").read_bytes(),
                          "voice2excel/web/app.js": b"console.log(1)", "voice2excel/hidden.py": b"x"})
    with pytest.raises(updater.UpdateError, match="ثبت‌نشده"):
        updater.inspect_update(extra)


def test_runtime_id_depends_on_python_and_libraries():
    a = updater.compute_runtime_id("3.12.10", ["numpy==2.5.4", "av==19.0.1"])
    assert a == updater.compute_runtime_id("3.12.4", ["av==19.0.1", "numpy==2.5.4"])  # فقط اصلی.فرعی و بی‌ترتیب
    assert a != updater.compute_runtime_id("3.12.10", ["numpy==2.5.5", "av==19.0.1"])
    assert a != updater.compute_runtime_id("3.13.0", ["numpy==2.5.4", "av==19.0.1"])
