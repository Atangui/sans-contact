import pytest

from sanscontact.power import PowerMachine, PowerState, Reason


def test_starts_off_and_never_activates_by_itself():
    machine = PowerMachine()
    assert machine.state is PowerState.OFF
    assert machine.tick(1e9) is None
    assert machine.engaged() is None
    assert not machine.camera_on


def test_full_cycle():
    m = PowerMachine(pause_timeout_s=30)
    t = m.activate()
    assert t.camera_started and m.state is PowerState.STANDBY and m.camera_on and not m.controls_cursor
    assert m.engaged().state is PowerState.ACTIVE and m.controls_cursor
    t = m.pointer_taken(Reason.PHYSICAL_MOUSE, now=100.0)
    assert t.left_active and m.state is PowerState.PAUSED and m.reason is Reason.PHYSICAL_MOUSE
    assert m.tick(129.9) is None
    assert m.pause_remaining(110.0) == pytest.approx(20.0)
    t = m.tick(130.0)
    assert t.camera_stopped and m.state is PowerState.OFF and m.reason is Reason.PAUSE_TIMEOUT


def test_engagement_from_pause_resumes_and_cancels_timeout():
    m = PowerMachine(pause_timeout_s=30)
    m.activate()
    m.engaged()
    m.pointer_taken(Reason.PHYSICAL_MOUSE, now=0.0)
    assert m.engaged().state is PowerState.ACTIVE
    assert m.tick(1000.0) is None
    assert m.pause_remaining(1000.0) is None


def test_hand_lost_returns_to_standby():
    m = PowerMachine()
    m.activate()
    m.engaged()
    t = m.hand_lost()
    assert t.state is PowerState.STANDBY and t.left_active and not t.camera_stopped


@pytest.mark.parametrize("setup", ["standby", "active", "paused"])
def test_deactivate_releases_camera_from_any_on_state(setup):
    m = PowerMachine()
    m.activate()
    if setup in ("active", "paused"):
        m.engaged()
    if setup == "paused":
        m.pointer_taken(Reason.ELEVATED_WINDOW, now=0.0)
    t = m.deactivate(Reason.SESSION_LOCKED)
    assert t.camera_stopped and m.state is PowerState.OFF and m.reason is Reason.SESSION_LOCKED
    assert m.deactivate() is None


def test_toggle():
    m = PowerMachine()
    assert m.toggle().state is PowerState.STANDBY
    assert m.toggle().state is PowerState.OFF


def test_pointer_taken_only_from_active_and_with_a_pause_reason():
    m = PowerMachine()
    m.activate()
    assert m.pointer_taken(Reason.PHYSICAL_MOUSE, now=0.0) is None
    with pytest.raises(ValueError):
        m.pointer_taken(Reason.USER, now=0.0)


def test_invalid_timeout():
    with pytest.raises(ValueError):
        PowerMachine(pause_timeout_s=0)
