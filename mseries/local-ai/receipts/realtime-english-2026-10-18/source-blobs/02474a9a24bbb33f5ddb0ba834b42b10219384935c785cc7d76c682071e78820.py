#!/usr/bin/python3
"""File-only, wall-paced speech benchmark; private receipts, no microphone or desktop input.

One engine process, three consecutive utterances, no discarded quality results.
Use an external quiet-admission supervisor; --worker never opens an audio device.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import resource
import sys
import time
import wave

REFERENCE = 'He hoped there would be stew for dinner, turnips and carrots and bruised potatoes and fat mutton pieces to be ladled out in thick, peppered, flour-fattened sauce'


def normalized(text):
    return re.findall(r'\w+', text.casefold())


def wer(reference, actual):
    a, b = normalized(reference), normalized(actual)
    row = list(range(len(b) + 1))
    for i, word in enumerate(a, 1):
        new = [i]
        for j, other in enumerate(b, 1):
            new.append(min(new[-1] + 1, row[j] + 1, row[j-1] + (word != other)))
        row = new
    return row[-1] / len(a)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine', choices=['unified-cpu', 'nemotron-cpu', 'nemotron-160-cpu', 'nemotron-560-cpu', 'moonshine-tiny-ort', 'moonshine-small-ort'], required=True)
    p.add_argument('--wav', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--runs', type=int, default=3)
    args = p.parse_args()
    if args.output.exists(): raise SystemExit('Refusing to overwrite completed or interrupted evidence')
    import numpy as np
    with wave.open(str(args.wav)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
        pcm = np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(np.float32) / 32768
    data = {'complete':False, 'engine':args.engine, 'kernel':platform.release(),
        'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'wav_sha256':hashlib.sha256(args.wav.read_bytes()).hexdigest(), 'duration_s':len(pcm)/16000,
        'microphone_recorded':False, 'owner_windows_opened':False, 'trials':[],
        'scope':'One public LibriSpeech clip, wall-paced 100ms input; no microphone/app insertion, not a general accuracy test. Model load separate; first trial retained, not discarded.'}
    def checkpoint():
        temp=args.output.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2)+'\n');temp.replace(args.output)
    checkpoint();loaded=time.monotonic()
    if args.engine.endswith('-cpu'):
        import transcribe_cpp as tc
        model=tc.Model(str(args.model),backend='cpu')
    else:
        from moonshine_voice import Transcriber, ModelArch
        arch=ModelArch.TINY_STREAMING if 'tiny' in args.engine else ModelArch.SMALL_STREAMING
        model=Transcriber(args.model,arch,update_interval=.3,options={'identify_speakers':'false'})
    data['load_s']=time.monotonic()-loaded;checkpoint()
    try:
        for run in range(args.runs):
            events=[];last='';start=time.monotonic();cpu_start=time.process_time()
            def record(text, final=False):
                nonlocal last
                if text!=last or final:
                    events.append({'wall_s':time.monotonic()-start,'text':text,'final':final});last=text
            if args.engine.endswith('-cpu'):
                session=model.session(n_threads=4);session.__enter__()
                options = ({'family':tc.ParakeetStreamOptions(att_context_right=1 if args.engine=='nemotron-160-cpu' else 6)}
                           if args.engine in ('nemotron-160-cpu','nemotron-560-cpu') else {})
                stream=session.stream(**options);stream.__enter__()
                def feed(chunk):
                    stream.feed(chunk);record(stream.text().display.strip())
                def finish():
                    stream.finalize();record(stream.text().display.strip(),True)
            else:
                stream=model.create_stream(update_interval=.3);lines={}
                def listener(event):
                    if hasattr(event,'error'): raise RuntimeError('Moonshine stream error')
                    lines[event.line.line_id]=event.line.text
                    record(' '.join(lines.values()))
                stream.add_listener(listener);stream.start()
                feed=lambda chunk:stream.add_audio(chunk.tolist(),16000)
                def finish():
                    transcript=stream.stop()
                    if transcript is None:raise RuntimeError('Moonshine finalization unavailable')
                    record(' '.join(line.text for line in transcript.lines),True)
            try:
                for offset in range(0,len(pcm),1600):
                    chunk=pcm[offset:offset+1600];due=start+(offset+len(chunk))/16000
                    time.sleep(max(0,due-time.monotonic()));feed(chunk)
                audio_end=start+len(pcm)/16000;finish()
            finally:
                if args.engine.endswith('-cpu'):stream.__exit__(None,None,None);session.__exit__(None,None,None)
                else:stream.close()
            first=next((e['wall_s'] for e in events if e['text'].strip()),None)
            data['trials'].append({'run':run+1,'events':events,'first_text_s':first,
                'final_after_audio_s':time.monotonic()-audio_end,'cpu_s':time.process_time()-cpu_start,
                'final_text':last,'normalized_wer':wer(REFERENCE,last),
                'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                'display_updates_before_audio_end':sum(bool(e['text']) and e['wall_s']<len(pcm)/16000 for e in events)})
            checkpoint()
    finally:model.close()
    data['complete']=True;checkpoint()
    print(json.dumps({'engine':args.engine,'complete':True,'trials':len(data['trials'])}),flush=True)


if __name__=='__main__':main()
