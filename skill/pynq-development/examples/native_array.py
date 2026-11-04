"""CPU ndarray/native-callable contract; NumPy optional, no library/device load."""
import json


def convert(image, native):
    import numpy as np
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8:
        raise TypeError("expected uint8 ndarray")
    if image.ndim != 3 or image.shape[2] != 3 or min(image.shape[:2]) <= 0:
        raise ValueError("expected positive HxWx3")
    source = np.ascontiguousarray(image)
    output = np.empty(image.shape, dtype=np.uint8, order="C")
    if native(source, output) != 0:
        raise RuntimeError("native returned nonzero status")
    return output


def main():
    import numpy as np
    image = np.arange(4 * 8 * 3, dtype=np.uint8).reshape(4, 8, 3)[:, ::2, :]
    before = image.copy()
    image.flags.writeable = False
    calls = []

    def mock_native(source, output):
        assert source.flags.c_contiguous and output.flags.c_contiguous
        calls.append(1)
        output[:] = source[..., ::-1]
        return 0

    output = convert(image, mock_native)
    assert calls == [1] and np.array_equal(image, before)
    assert np.array_equal(output, before[..., ::-1]) and not np.shares_memory(image, output)
    print(json.dumps(dict(scope="MOCK_NATIVE_ONLY", calls=len(calls),
                          shape=list(output.shape), input_unchanged=True)))


if __name__ == "__main__":
    main()
