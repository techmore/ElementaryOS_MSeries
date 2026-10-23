"""Supervised single-image engine adapter, with genuine intermediate previews."""
import json, sys, os, time, subprocess, resource, secrets, signal
from pathlib import Path
os.umask(0o077)


def supervised_child():
    import ctypes, signal, os
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(1,signal.SIGTERM,0,0,0)!=0 or os.getppid()==1:
        os._exit(127)


base = Path(sys.argv[1])
recipe = json.loads(sys.argv[2])
job, lock = base / 'current-job.json', base / 'generation.lock'
started, preview_count, first_preview = time.monotonic(), 0, None
proc, owned = None, False
images = base / 'images'
images.mkdir(parents=True, exist_ok=True)
name = 'local-' + str(time.time_ns())
output, metadata = images / (name + '.png'), images / (name + '.json')
preview_dir = base / 'previews' / name
preview_dir.mkdir(parents=True)
cancel = base / 'cancel.request'


def available():
    return int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines()
                    if x.startswith('MemAvailable:'))) * 1024


def publish(status, running, image='', **extra):
    data = dict(status=status, running=running,
                engine='stable-diffusion.cpp · local Vulkan build · backend details in run log',
                prompt=recipe['prompt'], image_path=str(image), recipe_path=str(metadata),
                preview_count=preview_count, elapsed_seconds=round(time.monotonic()-started, 2), **extra)
    temp = job.with_suffix('.tmp')
    temp.write_text(json.dumps(data))
    os.replace(temp, job)


def stop_child():
    if proc and proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()


try:
    batch = base / 'batch.lock'
    if batch.exists() and batch.read_text() != os.environ.get('MSERIES_SWEEP_ID', ''):
        raise RuntimeError('A sweep is active; wait for it or cancel it first.')
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    owned = True
    if cancel.exists():
        raise RuntimeError('Cancelled.')
    model = Path(recipe['model_id']).resolve()
    models = {
        'stable-diffusion-v1-5-pruned-emaonly-Q4_0.gguf': 3.0,
        'stable-diffusion-v1-5-pruned-emaonly-Q8_0.gguf': 3.5,
        'sd_xl_turbo_1.0_fp16.safetensors': 6.0,
    }
    if model.name not in models or model.parent != (base/'models').resolve() or not model.is_file():
        raise RuntimeError('Choose an installed model from Models, then load its starter defaults.')
    if recipe.get('lora_id'):
        raise RuntimeError('LoRA rendering is not qualified yet. Clear the adapter for this run.')
    if recipe['width'] != 512 or recipe['height'] != 512 or recipe['batch_size'] != 1:
        raise RuntimeError('Current local calibration supports 512 × 512 and one image at a time. Use Compare for a sequential sweep.')
    if recipe.get('sampler', 'euler') not in ('euler', 'euler_a'):
        raise RuntimeError('Select Euler or Euler ancestral for this engine.')
    if not 1 <= recipe.get('steps', 20) <= 50 or not 0 <= recipe.get('cfg_scale', 7) <= 15:
        raise RuntimeError('Steps or guidance are outside the supported range.')
    if 'turbo' in model.name and (recipe.get('steps',20) > 4 or recipe.get('cfg_scale',7) != 1):
        raise RuntimeError('Load SDXL Turbo defaults: 1–4 steps, engine CFG 1, no negative prompt.')
    required = (6 + models[model.name]) * 1024**3
    if available() < required:
        raise RuntimeError(f'This calibration needs {6+models[model.name]:g} GiB available, including the 6 GiB desktop reserve.')
    binary = base / 'engine/sd-cli'
    if not binary.is_file():
        raise RuntimeError('Install the local image engine using the documented engine setup.')
    if recipe['seed'] < 0:
        recipe['seed'] = secrets.randbelow(2147483647)
    recipe.update(engine_id='stable-diffusion.cpp local Vulkan build',
                  settings_note='Supervised local calibration. Intermediate images are projected latents. Peak memory is process RSS, excluding GPU allocations. Backend selection is retained in the run log.')
    receipt = model.with_suffix(model.suffix+'.json')
    if receipt.is_file():
        recipe['model_receipt'] = json.loads(receipt.read_text())
    source = base/'engine/source.json'
    if source.is_file():
        recipe['engine_receipt'] = json.loads(source.read_text())
    metadata.write_text(json.dumps(recipe, indent=2))
    publish('Loading local model…', True)
    command = [str(binary), '-m', str(model), '-p', recipe['prompt'], '-n', recipe['negative_prompt'],
               '-W', str(recipe['width']), '-H', str(recipe['height']), '--steps', str(recipe.get('steps',20)),
               '--cfg-scale', str(recipe.get('cfg_scale',7)), '--sampling-method', recipe.get('sampler','euler'),
               '--seed', str(recipe['seed']), '--preview', 'proj', '--preview-interval', '1',
               '--preview-path', str(preview_dir/'frame-%03d.png'), '--clip-on-cpu', '--vae-on-cpu',
               '-t', '2', '-o', str(output)]
    recipe['engine_arguments'] = command
    metadata.write_text(json.dumps(recipe, indent=2))
    minimum_available = available()
    with (images/(name+'.log')).open('w') as log:
        proc = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True, preexec_fn=supervised_child)
        last = None
        while proc.poll() is None:
            free = available()
            minimum_available = min(minimum_available, free)
            if free < 6*1024**3:
                stop_child()
                raise RuntimeError('Stopped to preserve the 6 GiB desktop memory reserve.')
            if cancel.exists():
                stop_child()
                raise RuntimeError('Cancelled by user.')
            frames = sorted(preview_dir.glob('frame-*.png'))
            if frames and frames[-1] != last and frames[-1].read_bytes().endswith(b'IEND\xaeB`\x82'):
                last = frames[-1]
                preview_count = len(frames)
                if first_preview is None:
                    first_preview = round(time.monotonic()-started,3)
                publish('Rendering · preview '+str(preview_count), True, last)
            if time.monotonic()-started > 900:
                stop_child()
                raise RuntimeError('Render stopped after the 15 minute calibration limit.')
            time.sleep(.25)
    if proc.returncode:
        raise RuntimeError('Image engine failed. Details: '+str(images/(name+'.log')))
    if not output.is_file() or not output.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
        raise RuntimeError('Engine returned no valid PNG.')
    recipe.update(image_path=str(output), elapsed_seconds=round(time.monotonic()-started,3),
                  peak_memory_mib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss//1024,
                  preview_count=len(list(preview_dir.glob('frame-*.png'))),
                  time_to_first_preview_seconds=first_preview,
                  minimum_available_mib=minimum_available//1048576)
    metadata.write_text(json.dumps(recipe, indent=2))
    publish('Complete · local render', False, output)
except Exception as error:
    stop_child()
    if owned:
        publish('Generation unavailable: '+str(error), False)
    print(str(error), file=sys.stderr)
    sys.exit(1)
finally:
    if owned:
        lock.unlink(missing_ok=True)
