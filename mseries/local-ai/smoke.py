"""Small correctness checks, not a performance benchmark or ANE qualification."""
import json
import numpy as np
import mlx.core as mx

info = mx.device_info()
assert 'Apple M1 Pro' in str(info), f'Unexpected device: {info}'
a = np.arange(64, dtype=np.float32).reshape(8, 8) / 8
b = np.flip(a, axis=0).copy()
result = mx.array(a) @ mx.array(b)
mx.eval(result)
np.testing.assert_allclose(np.array(result), a @ b, rtol=1e-5, atol=1e-5)
x = np.arange(64, dtype=np.int32)
shifted = (mx.array(x) << 3) ^ (mx.array(x) >> 1)
mx.eval(shifted)
np.testing.assert_array_equal(np.array(shifted), (x << 3) ^ (x >> 1))
print(json.dumps({'mlx': mx.__version__, 'device': str(info),
                  'checks': ['float32_matmul', 'int32_shifts_xor'], 'passed': True}, indent=2))
