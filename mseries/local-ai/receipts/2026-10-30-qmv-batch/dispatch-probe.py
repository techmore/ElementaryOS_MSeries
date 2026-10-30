import os
import mlx.core as mx
mx.random.seed(7)
w0=mx.random.normal((2048,2048)).astype(mx.bfloat16)
w,s,b=mx.quantize(w0,group_size=64,bits=4)
x=mx.random.normal((4,1,2048)).astype(mx.bfloat16)
mx.eval(w,s,b,x); mx.synchronize()
for v in ('0','1'):
 os.environ['MLX_OMARCHY_QMV_BATCH']=v
 print('MARK',v,flush=True)
 y=mx.quantized_matmul(x,w,s,b,transpose=True,group_size=64,bits=4)
 mx.eval(y); mx.synchronize()
 print('END',v,flush=True)
