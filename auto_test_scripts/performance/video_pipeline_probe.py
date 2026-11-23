"""Benchmark-only nested stage timers; never imported by normal playback."""
import threading
import time
import sys
from pathlib import Path
from collections import defaultdict
from PIL import Image
import psutil

class PipelineProbe:
    def __init__(self, vm):
        self.vm = vm
        self.lock = threading.RLock()
        self.enabled = False
        self.metrics = defaultdict(lambda: [0,0.,0.])
        self.samples = []
        self.originals = []
        self.process = psutil.Process()
        self._wrap(vm, '_decode_incremental', lambda path,first,last,vid,config: ('extract','extract_video_%02d'%vid))
        self._wrap(vm, '_run_window_stitch', lambda *a,**k: 'stitch')
        self._wrap(Image.Image, 'save', lambda im,fp,*a,**k: 'save_'+str(k.get('format') or (a[0] if a else 'unknown')))
        self._wrap(Image.Image, 'resize', lambda *a,**k: 'resize')
        self._wrap(Image.Image, 'copy', lambda *a,**k: 'copy')
        if (Path(sys.modules[type(vm).__module__].__file__).parent/'image_pipeline.py').is_file():
            from mulimgviewer.src.image_pipeline import MosaicPlan
            self._wrap(MosaicPlan,'_build',lambda *a,**k:'algorithm_mosaic')
        from mulimgviewer.src.video_decoder import DecoderSession
        original=DecoderSession.frames
        self.originals.append((DecoderSession,'frames',original))
        def frames(*args,**kwargs):
            iterator=original(*args,**kwargs)
            while True:
                enabled=self.enabled
                wall,cpu=time.perf_counter(),time.thread_time()
                try:
                    item=next(iterator)
                except StopIteration:
                    return
                finally:
                    if enabled:
                        wall,cpu=time.perf_counter()-wall,time.thread_time()-cpu
                        with self.lock:
                            if self.enabled:
                                metric=self.metrics['decode_next']
                                metric[0]+=1;metric[1]+=wall;metric[2]+=cpu
                yield item
        DecoderSession.frames=frames

    def _wrap(self, owner, name, label):
        original = getattr(owner, name)
        self.originals.append((owner,name,original))
        def measured(*args, **kwargs):
            if not self.enabled:
                return original(*args, **kwargs)
            category = label(*args, **kwargs)
            wall, cpu = time.perf_counter(), time.thread_time()
            try:
                return original(*args, **kwargs)
            finally:
                wall, cpu = time.perf_counter()-wall, time.thread_time()-cpu
                with self.lock:
                    if self.enabled:
                        for metric_label in ((category,) if isinstance(category,str) else category):
                            metric = self.metrics[metric_label]
                            metric[0] += 1
                            metric[1] += wall
                            metric[2] += cpu
        setattr(owner,name,measured)

    def start(self):
        with self.lock:
            self.metrics.clear()
            self.samples.clear()
            self.started = time.perf_counter()
            self.produced = self.vm._produced_pages
            with self.vm._decoder_bank.lock:
                self.decoded = sum(s.decoded for s in self.vm._decoder_bank.sessions.values())
            self.io = self.process.io_counters()
            self.enabled = True

    def sample(self):
        if not self.enabled:
            return
        vm, group = self.vm, self.vm._pipeline_workers
        with group.lock:
            row = dict(active=list(group.active), quota=list(group.limits), cap=group.total_budget,
                active_bytes=group.active_bytes, memory=group.memory_budget,
                queued=[len(q) for q in group.queues])
            busy={key[1] for key in group.keys if key[0]==0}
            queued=[job[4] for job in group.queues[0] if not job[0].cancelled()]
            row['busy_videos']=sorted(busy)
            row['key_blocked_jobs']=sum(key in busy for key in queued)
            row['queued_videos']=sorted(set(queued))
            row['runnable_videos']=sorted(set(queued)-busy)
        with vm._cache_guard:
            row['stitch_waiting'] = sum(getattr(f,'video_waiting_for_extract',False) for f in vm._window_stitches.values() if not f.done())
            row['stitch_ready'] = sum(not getattr(f,'video_waiting_for_extract',False) for f in vm._window_stitches.values() if not f.done())
        with self.lock:
            if self.enabled:
                self.samples.append(row)

    def finish(self, ended):
        if not hasattr(self,'started'):
            return dict(elapsed=0,produced=0,production_fps=None,decoded=0,metrics={},samples=[],io={},note='Warmup not completed')
        with self.lock:
            self.enabled = False
            metrics = {k:dict(calls=v[0],wall_seconds=v[1],thread_cpu_seconds=v[2]) for k,v in self.metrics.items()}
            samples = list(self.samples)
        with self.vm._decoder_bank.lock:
            decoded = sum(s.decoded for s in self.vm._decoder_bank.sessions.values())-self.decoded
        produced = self.vm._produced_pages-self.produced
        io = self.process.io_counters()
        return dict(elapsed=ended-self.started, produced=produced, decoded=decoded,
            production_fps=produced/(ended-self.started), metrics=metrics, samples=samples,
            io={name:getattr(io,name)-getattr(self.io,name) for name in io._fields},
            note='Timers are nested and may overlap across threads; do not sum stage and child times. IO counters include OS-cached logical file traffic, not physical disk saturation.')

    def close(self):
        for owner,name,original in reversed(self.originals):
            setattr(owner,name,original)
