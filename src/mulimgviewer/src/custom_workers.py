"""Priority-ordered image kernels; only metadata waits in the queue."""
import threading
from concurrent.futures import Future, ThreadPoolExecutor


class ImageWorkers:
    def __init__(self, workers, thread_name_prefix='custom-image'):
        self.limit=max(1,int(workers))
        self.pool=ThreadPoolExecutor(self.limit,thread_name_prefix=thread_name_prefix)
        self.lock=threading.RLock()
        self.queue=[]
        self.active=0
        self.closed=False
        self.serial=0
        self.busy_keys={}

    def submit(self,fn,*args,priority=lambda:0,resource_key=None,max_concurrency=1):
        future=Future()
        with self.lock:
            if self.closed:raise RuntimeError('Cannot schedule image kernels after shutdown')
            self.serial+=1
            self.queue.append((priority,self.serial,future,fn,args,resource_key,max(1,int(max_concurrency))))
            self._dispatch()
        return future

    def _dispatch(self):
        while not self.closed and self.active<self.limit and self.queue:
            # Evaluate the latest playback position, including reversals/jumps.
            eligible=[i for i,job in enumerate(self.queue) if job[2].cancelled() or
                job[5] is None or self.busy_keys.get(job[5],0)<job[6]]
            if not eligible:return
            index=min(eligible,key=lambda i:(self.queue[i][0](),self.queue[i][1]))
            job=self.queue.pop(index)
            if job[2].cancelled():continue
            self.active+=1
            if job[5] is not None:self.busy_keys[job[5]]=self.busy_keys.get(job[5],0)+1
            self.pool.submit(self._run,job)

    def _run(self,job):
        _,_,future,fn,args=job[:5]
        try:
            if future.set_running_or_notify_cancel():
                try:result=fn(*args)
                except BaseException as error:future.set_exception(error)
                else:future.set_result(result)
        finally:
            with self.lock:
                self.active-=1
                if job[5] is not None:
                    count=self.busy_keys[job[5]]-1
                    if count:self.busy_keys[job[5]]=count
                    else:self.busy_keys.pop(job[5],None)
                self._dispatch()

    def shutdown(self,wait=True,cancel_futures=False):
        with self.lock:
            self.closed=True
            queued=self.queue;self.queue=[]
        # Never invoke Future callbacks while holding the scheduler lock.
        for job in queued:job[2].cancel()
        # Dispatched wrappers must run to settle their public Futures. Only
        # our metadata queue is cancellable; cancelling wrappers strands callers.
        self.pool.shutdown(wait=wait,cancel_futures=False)
