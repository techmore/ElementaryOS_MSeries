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
@mx.compile
def rms_norm(value):
    return value * mx.rsqrt(mx.mean(value * value, axis=-1, keepdims=True) + 1e-5)
values = np.linspace(0.2, 2.0, 24 * 256, dtype=np.float32).reshape(1, 24, 256)
expected = values / np.sqrt(np.mean(values * values, axis=-1, keepdims=True) + 1e-5)
for _ in range(2):
    normalized = rms_norm(mx.array(values))
    mx.eval(normalized)
    np.testing.assert_allclose(np.array(normalized), expected, rtol=2e-5, atol=2e-5)
print(json.dumps({'mlx': mx.__version__, 'device': str(info),
                  'checks': ['float32_matmul', 'int32_shifts_xor', 'compiled_rsqrt_rmsnorm_twice'], 'passed': True}, indent=2))
