"""Real C compile/load tests;skip explicitly if compiler/NumPy unavailable."""
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from build_native import build, compiler
try:
    import numpy as np
except ImportError:
    np = None


@unittest.skipIf(compiler() is None or np is None, "NOT_RUN: real C ABI requires existing compiler and NumPy")
class NativeLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="native_abi_")
        try:
            cls.library = build(Path(cls.temp.name) / "lib")
        except BaseException:
            cls.temp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_native(self, code):
        # Load in a child so Windows releases the DLL before parent cleanup.
        examples = Path(__file__).resolve().parents[1] / 'examples'
        prelude = 'import sys,ctypes\nimport numpy as np\nsys.path.insert(0,sys.argv[1])\nfrom native_binding import NativeBgr\nfrom native_array import convert\nnative=NativeBgr(sys.argv[2])\n'
        result = subprocess.run([sys.executable, '-B', '-c', prelude + code, str(examples), str(self.library)],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_real_roi_readonly_input(self):
        self.run_native('image=np.arange(90,dtype=np.uint8).reshape(3,10,3)[:,::-2,:]\nimage.flags.writeable=False\noutput=convert(image,native)\nassert np.array_equal(output,image[...,::-1])\nassert not np.shares_memory(image,output)\n')

    def test_real_stride_padding_and_short_span(self):
        self.run_native('source=(ctypes.c_uint8*20)(*range(20))\ntarget=(ctypes.c_uint8*24)(*([165]*24))\nfn=native.function\nassert fn(source,20,10,target,24,12,2,2)==0\nassert list(target)[:6]==[2,1,0,5,4,3]\nassert list(target)[6:12]==[165]*6\nassert fn(source,15,10,target,24,12,2,2)==-1\n')

    def test_real_overlap_and_overflow_rejected(self):
        self.run_native('buffer=(ctypes.c_uint8*30)()\nfn=native.function\nassert fn(buffer,30,6,buffer,30,6,2,2)==-2\nhuge=ctypes.c_size_t(-1).value\nassert fn(buffer,30,6,buffer,30,6,huge,2)==-1\n')

    def test_binding_rejects_alias_before_c(self):
        self.run_native('image=np.zeros((2,2,3),dtype=np.uint8)\ntry:\n native(image,image)\nexcept ValueError:\n pass\nelse:\n raise AssertionError("alias accepted")\n')


if __name__ == "__main__":
    unittest.main()
