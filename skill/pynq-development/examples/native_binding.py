"""Explicit synchronous CPU ctypes binding;loading a library executes native code."""
import ctypes
from pathlib import Path


class NativeBgr:
    def __init__(self, library):
        path = Path(library).resolve(strict=True)
        self.library = ctypes.CDLL(str(path))
        self.library.bgr_abi_version.argtypes = []
        self.library.bgr_abi_version.restype = ctypes.c_uint32
        if self.library.bgr_abi_version() != 1:
            raise RuntimeError("unsupported native ABI")
        self.function = self.library.bgr_reverse
        pointer, size = ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t
        self.function.argtypes = [pointer, size, size, pointer, size, size, size, size]
        self.function.restype = ctypes.c_int

    def __call__(self, source, output):
        import numpy as np
        for image in (source, output):
            if not isinstance(image, np.ndarray) or image.dtype != np.uint8:
                raise TypeError("expected uint8 ndarray")
            if image.ndim != 3 or image.shape[2] != 3 or min(image.shape[:2]) <= 0 or not image.flags.c_contiguous:
                raise ValueError("expected nonempty contiguous HxWx3")
        if source.shape != output.shape or not output.flags.writeable or np.shares_memory(source, output):
            raise ValueError("distinct writable matching output required")
        pointer = ctypes.POINTER(ctypes.c_uint8)
        # Both ndarrays remain referenced until this synchronous call returns.
        return self.function(source.ctypes.data_as(pointer), source.nbytes, source.strides[0],
                             output.ctypes.data_as(pointer), output.nbytes, output.strides[0],
                             source.shape[1], source.shape[0])
