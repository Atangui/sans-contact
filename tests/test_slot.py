import threading

import numpy as np

from sanscontact.capture.slot import FrameSlot, LatestSlot


def frame(value):
    return np.full((4, 6, 3), value, dtype=np.uint8)


def test_only_the_newest_frame_is_kept():
    slot = FrameSlot()
    for v in (1, 2, 3):
        slot.publish(frame(v), t_ns=v)
    out, seq, t = slot.take(None, after_seq=0, timeout=0.1)
    assert out[0, 0, 0] == 3 and seq == 3 and t == 3
    assert slot.overwritten == 2
    assert slot.take(out, after_seq=seq, timeout=0.01) is None  # nothing newer


def test_take_copies_and_reuses_the_destination():
    slot = FrameSlot()
    source = frame(7)
    slot.publish(source, 1)
    source.fill(0)  # the published copy is independent from the caller's buffer
    dst = np.empty((4, 6, 3), dtype=np.uint8)
    out, _, _ = slot.take(dst, 0, 0.1)
    assert out is dst and int(dst[0, 0, 0]) == 7


def test_close_wipes_the_buffer_and_wakes_waiters():
    slot = FrameSlot()
    slot.publish(frame(9), 1)
    buffer = slot._buffer
    results = []
    waiter = threading.Thread(target=lambda: results.append(slot.take(None, after_seq=1, timeout=5)))
    waiter.start()
    slot.close()
    waiter.join(timeout=2)
    assert results == [None]
    assert not buffer.any()  # zeroed, not just dropped
    slot.publish(frame(5), 2)
    assert slot.closed and slot.take(None, 0, 0.01) is None


def test_latest_slot():
    slot = LatestSlot()
    slot.publish("a")
    slot.publish("b")
    assert slot.take(0, 0.1) == ("b", 2)
    assert slot.take(2, 0.01) is None
    slot.close()
    assert slot.closed and slot.take(0, 0.01) is None
