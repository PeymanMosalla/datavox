"""اجرای مدل تشخیص گفتار Silero (VAD همراه faster-whisper) فقط با numpy.

faster-whisper این مدل را با onnxruntime اجرا می‌کند؛ onnxruntime روی ویندوز ۷ بارگذاری نمی‌شود
(به توابع ویندوز ۸ به بعد نیاز دارد). این پیاده‌سازی همان گراف silero_vad_v6.onnx را با همان وزن‌ها
(مستقیم از همان فایل .onnx) محاسبه می‌کند؛ خروجی با onnxruntime در حد خطای اعشار float32 یکی است
(tests/test_vad_numpy.py). فقط وقتی onnxruntime در دسترس نباشد جایگزین می‌شود.
"""
from __future__ import annotations

import struct

import numpy as np

from .logger import get_logger

log = get_logger("vad")

_ONNX_FLOAT, _ONNX_INT64 = 1, 7


def _varint(buf: bytes, i: int) -> tuple[int, int]:
    shift = result = 0
    while True:
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if b < 0x80:
            return result, i
        shift += 7


def _fields(buf: bytes):
    """فیلدهای یک پیام protobuf: (شماره فیلد، نوع، مقدار)."""
    i, n = 0, len(buf)
    while i < n:
        key, i = _varint(buf, i)
        num, wire = key >> 3, key & 7
        if wire == 0:
            val, i = _varint(buf, i)
        elif wire == 1:
            val, i = buf[i:i + 8], i + 8
        elif wire == 2:
            ln, i = _varint(buf, i)
            val, i = buf[i:i + ln], i + ln
        elif wire == 5:
            val, i = buf[i:i + 4], i + 4
        else:
            raise ValueError(f"نوع فیلد protobuf پشتیبانی نمی‌شود: {wire}")
        yield num, wire, val


def onnx_initializers(path: str) -> dict[str, np.ndarray]:
    """وزن‌های ذخیره‌شده (initializer) یک فایل ONNX، بدون نیاز به بسته onnx."""
    with open(path, "rb") as f:
        model = f.read()
    graph = next(v for num, w, v in _fields(model) if num == 7 and w == 2)
    out = {}
    for num, w, tensor in _fields(graph):
        if num != 5 or w != 2:
            continue
        dims, dtype, name, raw = [], 0, "", b""
        for tnum, tw, tv in _fields(tensor):
            if tnum == 1:
                if tw == 0:
                    dims.append(tv)
                else:
                    j = 0
                    while j < len(tv):
                        d, j = _varint(tv, j)
                        dims.append(d)
            elif tnum == 2:
                dtype = tv
            elif tnum == 8:
                name = tv.decode("utf-8")
            elif tnum == 9:
                raw = tv
        if dtype == _ONNX_FLOAT:
            out[name] = np.frombuffer(raw, dtype="<f4").reshape(dims).copy()
        elif dtype == _ONNX_INT64:
            out[name] = np.frombuffer(raw, dtype="<i8").reshape(dims).copy()
    return out


def _conv1d(x: np.ndarray, w: np.ndarray, b: np.ndarray, stride: int) -> np.ndarray:
    """Conv1d با kernel=3 و padding=1 (x: N×C×T، w: M×C×3)."""
    xp = np.pad(x, ((0, 0), (0, 0), (1, 1)))
    out_len = (xp.shape[2] - 3) // stride + 1
    cols = np.stack([xp[:, :, k:k + stride * (out_len - 1) + 1:stride] for k in range(3)], axis=-1)
    return np.einsum("ncok,mck->nmo", cols, w, optimize=True) + b[None, :, None]


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


class NumpySileroVAD:
    """جایگزین faster_whisper.vad.SileroVADModel با همان ورودی و خروجی."""

    def __init__(self, path: str):
        w = onnx_initializers(path)
        self.basis = w["encoder.feature_extractor.forward_basis_buffer"][:, 0, :]  # 258×256
        self.convs = [(w[f"encoder.conv_layers.{i}.weight"], w[f"encoder.conv_layers.{i}.bias"], s)
                      for i, s in enumerate((1, 2, 2, 1))]
        self.w_ih = w["onnx::LSTM_209"][0]  # 512×128 (دروازه‌ها به ترتیب ONNX: i, o, f, c)
        self.w_hh = w["onnx::LSTM_210"][0]
        bias = w["onnx::LSTM_211"][0]
        self.b_lstm = bias[:512] + bias[512:]
        self.dec_w = w["decoder.conv1d.weight"][0, :, 0]  # 128
        self.dec_b = w["decoder.conv1d.bias"][0]

    def _probs(self, batch: np.ndarray, h: np.ndarray, c: np.ndarray):
        # استخراج ویژگی: قاب‌های ۲۵۶تایی با گام ۱۲۸ روی سیگنال بازتابی، سپس دامنه طیف
        x = np.pad(batch, ((0, 0), (128, 128)), mode="reflect")
        frames = np.lib.stride_tricks.sliding_window_view(x, 256, axis=1)[:, ::128, :]  # N×5×256
        spec = frames @ self.basis.T  # N×5×258
        spec = spec[:, 1:, :]
        mag = np.sqrt(spec[..., :129] ** 2 + spec[..., 129:] ** 2).transpose(0, 2, 1)  # N×129×4
        y = mag.astype(np.float32)
        for wt, bs, stride in self.convs:
            y = np.maximum(_conv1d(y, wt, bs, stride), 0)
        feats = y[:, :, 0]  # N×128
        gates_x = feats @ self.w_ih.T + self.b_lstm  # N×512
        hs = np.empty((feats.shape[0], 128), dtype=np.float32)
        h, c = h.reshape(128).copy(), c.reshape(128).copy()
        w_hh_t = self.w_hh.T.copy()
        for t in range(feats.shape[0]):
            g = gates_x[t] + h @ w_hh_t
            i, o, f = _sigmoid(g[:128]), _sigmoid(g[128:256]), _sigmoid(g[256:384])
            c = f * c + i * np.tanh(g[384:])
            h = o * np.tanh(c)
            hs[t] = h
        probs = _sigmoid(np.maximum(hs, 0) @ self.dec_w + self.dec_b).astype(np.float32)
        return probs, h.reshape(1, 1, 128), c.reshape(1, 1, 128)

    def __call__(self, audio: np.ndarray, num_samples: int = 512, context_size_samples: int = 64):
        # همان آماده‌سازی faster_whisper.vad.SileroVADModel.__call__
        assert audio.ndim == 1, "Input should be a 1D array"
        assert audio.shape[0] % num_samples == 0, "Input size should be a multiple of num_samples"
        batched = audio.astype(np.float32).reshape(-1, num_samples)
        context = batched[..., -context_size_samples:].copy()
        context[-1] = 0
        context = np.roll(context, 1, 0)
        batched = np.concatenate([context, batched], 1)
        h = np.zeros((1, 1, 128), dtype=np.float32)
        c = np.zeros((1, 1, 128), dtype=np.float32)
        outputs = []
        for i in range(0, batched.shape[0], 10000):
            out, h, c = self._probs(batched[i:i + 10000], h, c)
            outputs.append(out)
        return np.concatenate(outputs, axis=0)


def install_fallback() -> bool:
    """اگر onnxruntime بارگذاری نشود، VAD با numpy اجرا می‌شود. True یعنی جایگزین فعال شد."""
    try:
        import onnxruntime  # noqa: F401
        return False
    except Exception as e:  # ImportError یا خطای بارگذاری DLL روی ویندوزهای قدیمی
        from faster_whisper import vad

        if vad.SileroVADModel is not NumpySileroVAD:
            vad.SileroVADModel = NumpySileroVAD
            vad.get_vad_model.cache_clear()
            log.info("onnxruntime در دسترس نیست (%s)؛ تشخیص گفتار (VAD) با numpy اجرا می‌شود", type(e).__name__)
        return True
