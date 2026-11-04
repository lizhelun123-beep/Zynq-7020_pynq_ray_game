"""Optional NumPy/native-callable contract cases, never import PYNQ."""
import importlib.util
from pathlib import Path
import unittest
try:
    import numpy as np
except ImportError:
    np = None

path = Path(__file__).resolve().parents[1] / "examples/native_array.py"
spec = importlib.util.spec_from_file_location("native_array_example", path)
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)


@unittest.skipIf(np is None, "optional NumPy not installed")
class NativeArrayTests(unittest.TestCase):
    def check_image(self, image):
        before, writable = image.copy(), image.flags.writeable
        calls = []
        def native(source, output):
            calls.append(1)
            self.assertTrue(source.flags.c_contiguous and output.flags.c_contiguous)
            self.assertFalse(np.shares_memory(source, output))
            output[:] = source[..., ::-1]
            return 0
        output = example.convert(image, native)
        self.assertEqual(calls, [1])
        self.assertTrue(np.array_equal(image, before))
        self.assertEqual(image.flags.writeable, writable)
        self.assertTrue(np.array_equal(output, before[..., ::-1]))
        self.assertTrue(output.flags.owndata and output.flags.c_contiguous)
        self.assertFalse(np.shares_memory(output, image))

    def test_contiguous(self):
        self.check_image(np.arange(72, dtype=np.uint8).reshape(3, 8, 3))

    def test_strided_negative_and_readonly(self):
        base = np.arange(72, dtype=np.uint8).reshape(3, 8, 3)
        readonly = base.copy()
        readonly.flags.writeable = False
        for image in [base[:, ::2, :], base[::-1, ::-1, :], readonly]:
            with self.subTest(strides=image.strides):
                self.check_image(image)

    def test_invalid_type_and_dtype_never_call_native(self):
        for image in [[], np.zeros((2, 3, 3), np.float32), np.zeros((2, 3, 3), np.uint16)]:
            with self.subTest(type=type(image)), self.assertRaises(TypeError):
                example.convert(image, lambda *_: self.fail("native called"))

    def test_invalid_shape_never_call_native(self):
        for shape in [(3, 4), (3, 4, 4), (0, 4, 3), (3, 0, 3)]:
            with self.subTest(shape=shape), self.assertRaises(ValueError):
                example.convert(np.zeros(shape, np.uint8), lambda *_: self.fail("native called"))

    def test_nonzero_status_does_not_return_output(self):
        with self.assertRaises(RuntimeError):
            example.convert(np.zeros((2, 3, 3), np.uint8), lambda *_: 7)

    def test_native_exception_propagates_unchanged(self):
        marker = RuntimeError("native exception")
        def native(*_):
            raise marker
        with self.assertRaises(RuntimeError) as caught:
            example.convert(np.zeros((2, 3, 3), np.uint8), native)
        self.assertIs(caught.exception, marker)


if __name__ == "__main__":
    unittest.main()
