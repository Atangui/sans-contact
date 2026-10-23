"""Abstract input sources, so another device (an eye tracker, say) can be added later.

A source turns whatever it senses into ``Observation`` objects and hands over
only the newest one. The rest of the application never knows where they came
from.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

import numpy as np

from sanscontact.perception.types import HandObservation, Observation


class PointerSource(ABC):
    kind: str = "abstract"

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None:
        """Stop sensing and release the device immediately."""

    @abstractmethod
    def latest(self, after_seq: int, timeout: float) -> Observation | None: ...

    @property
    @abstractmethod
    def fps(self) -> float: ...


class HandLandmarkEngine(ABC):
    """Turns one RGB frame into hand landmarks. Implementations keep no frame."""

    @abstractmethod
    def detect(self, rgb: np.ndarray, timestamp_ms: int) -> list[HandObservation]: ...

    @abstractmethod
    def close(self) -> None: ...


EngineFactory = Callable[[], HandLandmarkEngine]
