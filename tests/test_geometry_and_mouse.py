import ctypes

import pytest

from sanscontact import _win32 as w
from sanscontact.geometry import Rect, clamp_to_screens, union
from sanscontact.interpretation.hand_pose import features
from sanscontact.interpretation.pointer import ActiveZone, reference_point, to_zone, zone_to_desktop
from sanscontact.output.mouse import MouseOutput, from_absolute, to_absolute
from tests.synthetic.hand_model import make_hand

# Layouts: single screen; primary on the right with a 150 % screen on the left (negative
# coordinates); three screens with different heights (dead areas in the bounding box).
SINGLE = [Rect(0, 0, 1920, 1200)]
LEFT_SECONDARY = [Rect(0, 0, 1920, 1200), Rect(-2560, -240, 0, 1200)]
MIXED = [Rect(0, 0, 2560, 1440), Rect(2560, 360, 4480, 1440), Rect(-1080, -480, 0, 1440)]


@pytest.mark.parametrize("screens", [SINGLE, LEFT_SECONDARY, MIXED])
def test_absolute_coordinates_round_trip_on_every_pixel_column(screens):
    desk = union(screens)
    for x in range(desk.left, desk.right, 7):
        nx, _ = to_absolute(x, desk.top, desk)
        assert 0 <= nx <= 65535
        assert from_absolute(nx, 0, desk)[0] == x
    for y in range(desk.top, desk.bottom, 5):
        _, ny = to_absolute(desk.left, y, desk)
        assert from_absolute(0, ny, desk)[1] == y


def test_union_and_negative_origin():
    desk = union(LEFT_SECONDARY)
    assert desk == Rect(-2560, -240, 1920, 1200)
    assert to_absolute(-2560, -240, desk) == (7, 22)  # first pixel, aimed at its centre


def test_clamp_to_screens_avoids_dead_areas():
    assert clamp_to_screens(3000, 100, MIXED) == (3000, 360)  # above the short screen: down onto it
    assert clamp_to_screens(-500, -479, MIXED) == (-500, -479)
    assert clamp_to_screens(10_000, 10_000, MIXED) == (4479, 1439)


def test_mirrored_mapping_hand_right_means_cursor_right():
    zone = ActiveZone(0.2, 0.15, 0.8, 0.75)
    left_in_image = to_zone(0.3, 0.5, zone)
    right_in_image = to_zone(0.7, 0.5, zone)
    assert left_in_image[0] > right_in_image[0]  # the image is mirrored
    assert to_zone(0.5, 0.45, zone) == pytest.approx((0.5, 0.5))
    assert to_zone(0.0, 0.0, zone) == (1.0, 0.0)  # clamped


def test_zone_covers_the_whole_desktop():
    desk = union(LEFT_SECONDARY)
    assert zone_to_desktop(0.0, 0.0, desk) == (desk.left, desk.top)
    assert zone_to_desktop(1.0, 1.0, desk) == (desk.right - 1, desk.bottom - 1)


def test_reference_point_is_stable_not_the_fingertip():
    hand = make_hand("open", center=(0.4, 0.6))
    pose = features(hand, 4 / 3)
    assert reference_point(hand, pose, "palm_center") == pytest.approx((0.4, 0.6))
    index_base = reference_point(hand, pose, "index_mcp")
    assert index_base == pytest.approx(tuple(hand.landmarks[5, :2]))


def test_input_structure_has_the_win32_size():
    assert ctypes.sizeof(w.INPUT) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)


class FakeDesk:
    def __init__(self):
        self.sent = []
        self.cursor = (0, 0)

    def send(self, events):
        for e in events:
            self.sent.append((e.mi.dx, e.mi.dy, e.mi.dwFlags))
            if e.mi.dwFlags & w.MOUSEEVENTF_ABSOLUTE:
                self.cursor = from_absolute(e.mi.dx, e.mi.dy, Rect(0, 0, 1920, 1200))
        return len(events)

    def read(self):
        return self.cursor


def make_mouse():
    desk = FakeDesk()
    mouse = MouseOutput(send=desk.send, read_cursor=desk.read)
    mouse.set_desktop(Rect(0, 0, 1920, 1200))
    return mouse, desk


def test_move_uses_absolute_virtual_desktop_coordinates():
    mouse, desk = make_mouse()
    assert mouse.move_to(960, 600)
    flags = desk.sent[-1][2]
    assert flags & w.MOUSEEVENTF_ABSOLUTE and flags & w.MOUSEEVENTF_VIRTUALDESK and flags & w.MOUSEEVENTF_MOVE
    assert desk.cursor == (960, 600)
    assert mouse.moved_externally(tolerance=2) is False


def test_physical_mouse_is_detected():
    mouse, desk = make_mouse()
    assert mouse.moved_externally(2) is False  # nothing injected yet
    mouse.move_to(100, 100)
    desk.cursor = (102, 101)
    assert mouse.moved_externally(2) is False
    desk.cursor = (140, 100)
    assert mouse.moved_externally(2) is True


def test_unreadable_cursor_reports_none():
    mouse = MouseOutput(send=lambda events: len(events), read_cursor=lambda: None)
    assert mouse.moved_externally(2) is None


def test_release_all_releases_only_what_we_pressed():
    mouse, desk = make_mouse()
    mouse.release_all()
    assert desk.sent == []
    mouse.press("left")
    mouse.press("right")
    desk.sent.clear()
    mouse.release_all()
    released = sorted(flags for _, _, flags in desk.sent)
    assert released == sorted([w.MOUSEEVENTF_LEFTUP, w.MOUSEEVENTF_RIGHTUP])
    assert mouse.pressed == set()


def test_move_without_desktop_is_refused():
    with pytest.raises(RuntimeError):
        MouseOutput(send=lambda e: 1, read_cursor=lambda: (0, 0)).move_to(1, 1)
