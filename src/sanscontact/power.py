"""The on/off state machine: the single source of truth for the whole application.

| State   | Camera                    | Cursor                          |
|---------|---------------------------|---------------------------------|
| OFF     | off                       | free                            |
| STANDBY | on                        | free, waits for the engagement  |
| ACTIVE  | on                        | driven by the hand              |
| PAUSED  | on, released after timeout| free, with the reason           |

The machine is pure: it never touches the camera or the mouse itself. The
controller applies the side effects of each transition it returns.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PowerState(StrEnum):
    OFF = "off"
    STANDBY = "standby"
    ACTIVE = "active"
    PAUSED = "paused"


class Reason(StrEnum):
    STARTUP = "startup"
    USER = "user"
    ENGAGED = "engaged"
    HAND_LOST = "hand_lost"
    PHYSICAL_MOUSE = "physical_mouse"
    ELEVATED_WINDOW = "elevated_window"
    SECURE_DESKTOP = "secure_desktop"
    PAUSE_TIMEOUT = "pause_timeout"
    SESSION_LOCKED = "session_locked"
    SESSION_CHANGED = "session_changed"
    SUSPEND = "suspend"
    DISPLAY_OFF = "display_off"
    CAMERA_BUSY = "camera_busy"
    CAMERA_LOST = "camera_lost"
    NO_CAMERA = "no_camera"
    CONSENT_DECLINED = "consent_declined"
    DATA_DELETED = "data_deleted"
    ERROR = "error"
    EXIT = "exit"


PAUSE_REASONS = frozenset({Reason.PHYSICAL_MOUSE, Reason.ELEVATED_WINDOW, Reason.SECURE_DESKTOP})


@dataclass(frozen=True)
class Transition:
    previous: PowerState
    state: PowerState
    reason: Reason

    @property
    def camera_started(self) -> bool:
        return self.previous is PowerState.OFF and self.state is not PowerState.OFF

    @property
    def camera_stopped(self) -> bool:
        return self.previous is not PowerState.OFF and self.state is PowerState.OFF

    @property
    def left_active(self) -> bool:
        return self.previous is PowerState.ACTIVE and self.state is not PowerState.ACTIVE


class PowerMachine:
    """Explicit four-state machine. Every method returns the transition it made, or None."""

    def __init__(self, pause_timeout_s: float = 30.0) -> None:
        if pause_timeout_s <= 0:
            raise ValueError("pause_timeout_s must be positive")
        self.pause_timeout_s = pause_timeout_s
        self.state = PowerState.OFF
        self.reason = Reason.STARTUP
        self._paused_at: float | None = None

    @property
    def camera_on(self) -> bool:
        return self.state is not PowerState.OFF

    @property
    def controls_cursor(self) -> bool:
        return self.state is PowerState.ACTIVE

    def activate(self) -> Transition | None:
        if self.state is not PowerState.OFF:
            return None
        return self._go(PowerState.STANDBY, Reason.USER)

    def deactivate(self, reason: Reason = Reason.USER) -> Transition | None:
        if self.state is PowerState.OFF:
            return None
        return self._go(PowerState.OFF, reason)

    def toggle(self) -> Transition | None:
        return self.activate() if self.state is PowerState.OFF else self.deactivate(Reason.USER)

    def engaged(self) -> Transition | None:
        if self.state not in (PowerState.STANDBY, PowerState.PAUSED):
            return None
        return self._go(PowerState.ACTIVE, Reason.ENGAGED)

    def hand_lost(self) -> Transition | None:
        if self.state is not PowerState.ACTIVE:
            return None
        return self._go(PowerState.STANDBY, Reason.HAND_LOST)

    def pointer_taken(self, reason: Reason, now: float) -> Transition | None:
        """The cursor can no longer be driven (physical mouse, elevated window...)."""
        if reason not in PAUSE_REASONS:
            raise ValueError(f"{reason} is not a pause reason")
        if self.state is not PowerState.ACTIVE:
            return None
        transition = self._go(PowerState.PAUSED, reason)
        self._paused_at = now
        return transition

    def tick(self, now: float) -> Transition | None:
        """Release the camera once the pause has lasted ``pause_timeout_s``."""
        remaining = self.pause_remaining(now)
        if remaining is not None and remaining <= 0:
            return self._go(PowerState.OFF, Reason.PAUSE_TIMEOUT)
        return None

    def pause_remaining(self, now: float) -> float | None:
        if self.state is not PowerState.PAUSED or self._paused_at is None:
            return None
        return self.pause_timeout_s - (now - self._paused_at)

    def _go(self, state: PowerState, reason: Reason) -> Transition:
        transition = Transition(self.state, state, reason)
        self.state = state
        self.reason = reason
        if state is not PowerState.PAUSED:
            self._paused_at = None
        return transition
