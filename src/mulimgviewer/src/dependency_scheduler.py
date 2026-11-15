"""Nonblocking dependency continuations. Only ready computation enters workers.

Coroutine steps run briefly on one metadata dispatcher; yielding a Future
releases that dispatcher immediately. Results contain paths/metadata, not pixels.
Closing drains continuations before cache leases can be reclaimed.
"""
import threading
from concurrent.futures import Future, CancelledError, wait


class _Dispatcher:
    """One metadata thread; drain even while Python closes compute executors.

    A ThreadPoolExecutor wrapper that dispatches its next queued item on
    completion can lose that continuation during interpreter shutdown.
    This thread consumes the metadata queue directly, without new pool submits.
    """
    def __init__(self):
        self.condition=threading.Condition()
        self.queue=[];self.serial=0;self.closed=False
        self.thread=threading.Thread(target=self._run,name='pipeline-dispatch')
        self.thread.start()

    def submit(self,function,*args,priority=lambda:0):
        result=Future()
        with self.condition:
            if self.closed:raise RuntimeError('Metadata dispatcher is closing')
            self.serial+=1
            self.queue.append((priority,self.serial,result,function,args))
            self.condition.notify()
        return result

    def _run(self):
        while True:
            with self.condition:
                while not self.queue and not self.closed:self.condition.wait()
                if not self.queue:return
                index=min(range(len(self.queue)),key=lambda i:(self.queue[i][0](),self.queue[i][1]))
                _,_,result,function,args=self.queue.pop(index)
            if result.set_running_or_notify_cancel():
                try:result.set_result(function(*args))
                except BaseException as error:result.set_exception(error)

    def shutdown(self,wait=True):
        with self.condition:
            self.closed=True;self.condition.notify_all()
        if wait and threading.current_thread() is not self.thread:self.thread.join()


def gather(futures, return_exceptions=False):
    """Settle ALL dependencies, including failures, before releasing readers."""
    futures=tuple(futures)
    result=Future();result.set_running_or_notify_cancel()
    if not futures:
        result.set_result([]);return result
    lock=threading.Lock();remaining=[len(futures)]
    def settled(_):
        with lock:
            remaining[0]-=1
            last=remaining[0]==0
        if last:
            values=[];error=None
            for future in futures:
                try:values.append(future.result())  # All are already complete.
                except BaseException as exception:
                    values.append(exception)
                    if error is None:error=exception
            if error is not None and not return_exceptions:result.set_exception(error)
            else:result.set_result(values)
    for future in futures:future.add_done_callback(settled)
    return result


def run_inline(steps):
    """Compatibility for explicit synchronous export/headless callers."""
    value=None;error=None;first=True
    try:
        while True:
            try:
                pending=next(steps) if first else steps.throw(error) if error is not None else steps.send(value)
                first=False
            except StopIteration as done:return done.value
            if not isinstance(pending,Future):raise TypeError('Expected Future dependency')
            try:value=pending.result();error=None
            except BaseException as exception:value=None;error=exception
    finally:steps.close()


def prepared(steps, stack):
    """Enter a generator-backed cache lease without waiting on a worker."""
    stack.callback(steps.close)
    value=None;error=None;first=True
    while True:
        pending=next(steps) if first else steps.throw(error) if error is not None else steps.send(value)
        first=False
        if not isinstance(pending,Future):return pending
        try:value=yield pending;error=None
        except BaseException as exception:value=None;error=exception


class DependencyScheduler:
    def __init__(self):
        self.lock=threading.RLock()
        self.dispatcher=_Dispatcher()
        self.tasks={}
        self.closing=False
        self.finished=0

    def start(self,function,*args,priority=lambda:0):
        result=Future()
        # Cancellation uses generation/window predicates. The promise remains
        # running until cleanup completes; cancel() must not release live leases.
        result.set_running_or_notify_cancel()
        task=dict(future=result,function=function,args=args,steps=None,priority=priority,state='ready')
        with self.lock:
            if self.closing:raise RuntimeError('Dependency scheduler is closing')
            self.tasks[result]=task
            try:self.dispatcher.submit(self._step,task,None,None,True,priority=priority)
            except BaseException:
                self.tasks.pop(result,None)
                raise
        return result

    def submit(self,executor,function,*args,dependencies=(),priority=lambda:0):
        def steps():
            if dependencies:yield gather(dependencies)
            value=yield executor.submit(function,*args)
            # A ready stage may itself construct another asynchronous graph.
            while isinstance(value,Future):value=yield value
            return value
        return self.start(steps,priority=priority)

    def _resume(self,task,pending):
        try:value=pending.result();error=None  # Callback: never blocks.
        except BaseException as exception:value=None;error=exception
        with self.lock:
            task['state']='ready'
            draining=self.closing
            if not draining:
                self.dispatcher.submit(self._step,task,value,error,False,priority=task['priority'])
        # Interpreter shutdown forbids new ThreadPoolExecutor submissions.
        # Closing continuations only unwind leases/cancellation and run on the
        # completion thread, so draining needs no newly submitted wrapper.
        if draining:self._step(task,value,error,False)

    def _step(self,task,value,error,first):
        try:
            task['state']='running'
            if first:task['steps']=task['function'](*task['args'])
            steps=task['steps']
            pending=next(steps) if first else steps.throw(error) if error is not None else steps.send(value)
            if not isinstance(pending,Future):raise TypeError('Coroutine must yield a Future')
            with self.lock:task['state']='waiting'
            pending.add_done_callback(lambda future:self._resume(task,future))
            return
        except StopIteration as done:
            task['future'].set_result(done.value)
        except BaseException as exception:
            task['future'].set_exception(exception)
        finally:
            if task['future'].done():
                with self.lock:
                    self.tasks.pop(task['future'],None);self.finished+=1
                    task['function']=None;task['args']=();task['steps']=None;task['priority']=lambda:0
                    stop=self.closing and not self.tasks
                if stop:self.dispatcher.shutdown(wait=False)

    def snapshot(self):
        with self.lock:
            return dict(pending=len(self.tasks),waiting=sum(t['state']=='waiting' for t in self.tasks.values()),finished=self.finished)

    def shutdown(self,wait_for_tasks=False):
        with self.lock:
            self.closing=True;tasks=list(self.tasks)
        if wait_for_tasks:
            wait(tasks)
            self.dispatcher.shutdown(wait=True)
        elif not tasks:self.dispatcher.shutdown(wait=False)
