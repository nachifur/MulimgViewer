"""Global processing budgets and bounded two-level cache windows (no wx)."""
from __future__ import annotations
import math
import os
import sys
from decimal import Decimal, InvalidOperation
from typing import NamedTuple

from .thread_optimizer import available_memory_bytes


class ResourceBudget(NamedTuple):
    mode: int
    workers: int
    memory: int | None


def positive_cache_integer(raw):
    """Validate before conversion: 0.5 must never silently become 0 or 1."""
    try:
        value = Decimal(str(raw).strip())
        if not value.is_finite() or value < 1 or value > sys.maxsize or value != value.to_integral_value():
            raise ValueError('Enter an integer greater than or equal to 1')
        return int(value)
    except (InvalidOperation, TypeError, ValueError, OverflowError) as ex:
        raise ValueError('Enter an integer greater than or equal to 1') from ex


def resource_budget(mode, video=False, cpus=None, available=None):
    """Soft worker/RAM ceilings, not an OS CPU percentage or memory quota.

    One-core machines still need two video pipeline lanes; their work shares
    the CPU. Memory is sampled at policy changes, rather than per GUI paint.
    """
    mode = max(1, min(4, int(mode)))
    cpu_fraction, memory_fraction = ((.25, .15), (.5, .30), (.75, .50), (1., .75))[mode - 1]
    cpus = max(1, int(cpus or os.cpu_count() or 1))
    available = available_memory_bytes() if available is None else available
    return ResourceBudget(mode, max(2 if video else 1, math.floor(cpus * cpu_fraction)),
                          int(available * memory_fraction) if available is not None else None)


def cache_window(batch, total, radius, multiplier, previous=None):
    """Retain an anchored outer window until within one inner radius of an edge."""
    radius, multiplier = max(1, int(radius)), max(1, int(multiplier))
    end = max(0, int(total) - 1)
    batch = max(0, min(end, int(batch)))
    if previous is not None and multiplier >= 2:
        lo, hi = previous
        if (lo <= batch <= hi and (lo == 0 or batch - lo > radius)
                and (hi == end or hi - batch > radius)):
            return previous
    return max(0, batch - radius * multiplier), min(end, batch + radius * multiplier)


def composition_workers(budget, memory, output_pixels=0, input_pixels=0):
    """All image lanes compose; cap simultaneous working sets by the RAM budget."""
    working = max(64 * 1024 ** 2, 16 * output_pixels + 9 * input_pixels)
    return max(1, min(int(budget), int(memory) // working if memory is not None else int(budget)))
