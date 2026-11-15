"""Integer minimax allocation for decode/process/stitch/compose workloads.

Work is measured permit-seconds per final page, excluding dependency/queue
waits. Targets are soft: runnable stages can borrow idle capacity. Arbitrary
plugins/GIL/IO make the linear work model an estimate, not a global guarantee.
"""
import math
from typing import NamedTuple


class StageAllocation(NamedTuple):
    targets: tuple
    period: float
    reason: str


def allocate_stages(budget, work, caps=None, memory=None, memory_budget=None):
    budget=max(1,int(budget))
    work=tuple(max(0.,float(value)) if math.isfinite(float(value)) else 0. for value in work)
    count=len(work)
    caps=tuple(max(0,min(budget,int(value))) for value in (caps if caps is not None else [budget]*count))
    memory=tuple(max(0,int(value)) for value in (memory if memory is not None else [0]*count))
    if len(caps)!=count or len(memory)!=count:raise ValueError('Stage vector lengths differ')
    active=[i for i in range(count) if work[i]>0 and caps[i]>0]
    if not active:return StageAllocation((0,)*count,0.,'idle')
    # An optimum must equal work[i]/n for one bottleneck stage. Test these
    # O(stages*budget) breakpoints rather than enumerating O(budget**stages).
    periods=sorted({work[i]/n for i in active for n in range(1,caps[i]+1)})
    for period in periods:
        targets=[0]*count
        for i in active:targets[i]=max(1,math.ceil(work[i]/period-1e-10))
        if any(targets[i]>caps[i] for i in active) or sum(targets)>budget:continue
        used=sum(n*m for n,m in zip(targets,memory))
        if memory_budget is not None and used>memory_budget:continue
        # Use spare lanes where they most reduce the next-stage service time.
        while sum(targets)<budget:
            candidates=[i for i in active if targets[i]<caps[i] and
                (memory_budget is None or used+memory[i]<=memory_budget)]
            if not candidates:break
            i=max(candidates,key=lambda i:(work[i]/targets[i]-work[i]/(targets[i]+1),i))
            targets[i]+=1;used+=memory[i]
        return StageAllocation(tuple(targets),max(work[i]/targets[i] for i in active),'minimax')
    # Too few lanes/RAM for every stage simultaneously: targets express
    # preferences only. Admission still time-shares every ready, fitting stage.
    targets=[0]*count;used=0
    for _ in range(budget):
        candidates=[i for i in active if targets[i]<caps[i] and
            (memory_budget is None or used+memory[i]<=memory_budget)]
        if not candidates:break
        i=max(candidates,key=lambda i:(work[i]/(targets[i]+1),i))
        targets[i]+=1;used+=memory[i]
    return StageAllocation(tuple(targets),sum(work[i] for i in active)/budget,'time-share')
