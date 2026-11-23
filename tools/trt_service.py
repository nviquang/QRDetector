"""Dịch vụ detect QR bằng TensorRT trên GPU Jetson, chạy bằng Python 3.6 của JetPack (máy chủ, không trong Docker).

App chạy trong container Python 3.11 không có binding TensorRT (JetPack 4.6 chỉ có bản Python 3.6), nên detect GPU
tách ra tiến trình này. App (``qr/detector_onnx.py``, ``backend="tensorrt"``) ghi tensor 1×3×H×W float16 đã letterbox
vào ``/dev/shm/qrdetector-trt.in`` rồi gửi (H, W) qua Unix socket ``/dev/shm/qrdetector-trt.sock``; dịch vụ chạy
engine và trả đầu ra YOLO 5×N float32. Hậu xử lý (NMS, quad) vẫn ở app như bộ phát hiện ONNX/OpenVINO.

    python3 tools/trt_service.py [--engine qr/models/qrdet_n_detect_fp16.engine]

Engine tạo bằng ``tools/build_trt_engine.sh``. ``docker/jetson/run.sh`` tự chạy dịch vụ này khi có engine.
Viết cho Python 3.6, numpy 1.13 (không dataclass, không ``from __future__ import annotations``).
"""

import argparse
import ctypes
import logging
import mmap
import os
import socket
import struct
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ENGINE = os.path.join(ROOT, "qr", "models", "qrdet_n_detect_fp16.engine")
SOCKET_PATH = "/dev/shm/qrdetector-trt.sock"
SHM_PATH = "/dev/shm/qrdetector-trt.in"
MAGIC = b"QRT1"
REQUEST = struct.Struct("<4sII")          # magic, H, W
RESPONSE = struct.Struct("<4sIII")        # magic, status (0 = ok), hàng, cột (lỗi: cột = số byte thông báo)
MAX_SIDE = 2144                           # khớp --maxShapes của tools/build_trt_engine.sh
SHM_BYTES = 3 * MAX_SIDE * MAX_SIDE * 2   # float16

log = logging.getLogger("trt_service")


class Cuda(object):
    H2D, D2H = 1, 2

    def __init__(self):
        lib = None
        for name in ("libcudart.so", "libcudart.so.10.2", "/usr/local/cuda/lib64/libcudart.so"):
            try:
                lib = ctypes.CDLL(name)
                break
            except OSError:
                continue
        if lib is None:
            raise OSError("không nạp được libcudart")
        self._lib = lib

    def _check(self, code, what):
        if code != 0:
            raise RuntimeError("%s lỗi CUDA %d" % (what, code))

    def malloc(self, nbytes):
        ptr = ctypes.c_void_p()
        self._check(self._lib.cudaMalloc(ctypes.byref(ptr), ctypes.c_size_t(nbytes)), "cudaMalloc")
        return ptr.value

    def copy(self, dst, src, nbytes, kind):
        self._check(self._lib.cudaMemcpy(ctypes.c_void_p(dst), ctypes.c_void_p(src), ctypes.c_size_t(nbytes),
                                         ctypes.c_int(kind)), "cudaMemcpy")


class Engine(object):
    def __init__(self, path):
        import tensorrt as trt
        self._trt = trt
        logger = trt.Logger(trt.Logger.WARNING)
        with open(path, "rb") as f, trt.Runtime(logger) as runtime:
            self.engine = runtime.deserialize_cuda_engine(f.read())
        if self.engine is None:
            raise RuntimeError("không đọc được engine %s" % path)
        self.context = self.engine.create_execution_context()
        self.in_dtype = trt.nptype(self.engine.get_binding_dtype(0))
        self.out_dtype = trt.nptype(self.engine.get_binding_dtype(1))
        self.cuda = Cuda()
        self.d_in = self.cuda.malloc(3 * MAX_SIDE * MAX_SIDE * 4)
        anchors = sum((MAX_SIDE // s) ** 2 for s in (8, 16, 32))
        self.d_out = self.cuda.malloc(5 * anchors * 4)
        log.info("engine %s input=%s output=%s", os.path.basename(path), self.in_dtype.__name__,
                 self.out_dtype.__name__)

    def run(self, tensor_f16, h, w):
        """tensor_f16: mảng float16 C-contiguous 1×3×H×W. Trả mảng float32 (hàng, cột)."""
        if not self.context.set_binding_shape(0, (1, 3, h, w)):
            raise ValueError("kích thước %dx%d ngoài profile của engine" % (h, w))
        data = tensor_f16 if self.in_dtype == np.float16 else tensor_f16.astype(self.in_dtype)
        data = np.ascontiguousarray(data)
        self.cuda.copy(self.d_in, data.ctypes.data, data.nbytes, Cuda.H2D)
        if not self.context.execute_v2([self.d_in, self.d_out]):
            raise RuntimeError("execute_v2 thất bại")
        shape = tuple(self.context.get_binding_shape(1))        # (1, 5, N)
        out = np.empty(shape, self.out_dtype)
        self.cuda.copy(out.ctypes.data, self.d_out, out.nbytes, Cuda.D2H)
        return out.reshape(shape[1], shape[2]).astype(np.float32)


def recv_exact(conn, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise EOFError
        buf.extend(chunk)
    return bytes(buf)


def serve(engine, socket_path=SOCKET_PATH, shm_path=SHM_PATH):
    with open(shm_path, "wb") as f:
        f.truncate(SHM_BYTES)
    os.chmod(shm_path, 0o666)
    shm_file = open(shm_path, "r+b")
    shm = mmap.mmap(shm_file.fileno(), SHM_BYTES)
    if os.path.exists(socket_path):
        os.unlink(socket_path)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(socket_path)
    os.chmod(socket_path, 0o666)
    server.listen(4)
    log.info("sẵn sàng socket=%s shm=%s", socket_path, shm_path)
    while True:
        conn, _ = server.accept()
        log.info("app kết nối")
        try:
            while True:
                magic, h, w = REQUEST.unpack(recv_exact(conn, REQUEST.size))
                if magic != MAGIC:
                    raise ValueError("sai magic")
                try:
                    if h > MAX_SIDE or w > MAX_SIDE or h % 32 or w % 32:
                        raise ValueError("kích thước %dx%d không hợp lệ" % (h, w))
                    tensor = np.frombuffer(shm, np.float16, 3 * h * w).reshape(1, 3, h, w)
                    out = engine.run(tensor, h, w)
                    conn.sendall(RESPONSE.pack(MAGIC, 0, out.shape[0], out.shape[1]) + out.tobytes())
                except (ValueError, RuntimeError) as exc:
                    msg = str(exc).encode("utf-8")
                    log.warning("lỗi: %s", exc)
                    conn.sendall(RESPONSE.pack(MAGIC, 1, 0, len(msg)) + msg)
        except EOFError:
            log.info("app ngắt kết nối")
        except Exception as exc:     # client gửi sai giao thức: đóng kết nối đó, dịch vụ chạy tiếp
            log.warning("đóng kết nối: %s", exc)
        finally:
            conn.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--engine", default=DEFAULT_ENGINE)
    ap.add_argument("--socket", default=SOCKET_PATH)
    ap.add_argument("--shm", default=SHM_PATH)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s trt_service %(message)s")
    if not os.path.isfile(args.engine):
        log.error("thiếu engine %s — chạy tools/build_trt_engine.sh", args.engine)
        return 2
    serve(Engine(args.engine), args.socket, args.shm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
