import math

import numpy as np
import pytest

from sanscontact.perception import hand_geometry as g
from tests.synthetic.hand_model import make_hand

W, H = 640, 480


def test_anchor_layout_matches_the_palm_model():
    anchors = g.ssd_anchors()
    assert anchors.shape == (2016, 2)
    assert anchors[0] == pytest.approx((0.5 / 24, 0.5 / 24)) and (anchors[0] == anchors[1]).all()
    assert anchors[1152] == pytest.approx((0.5 / 12, 0.5 / 12))
    assert (anchors[1152:1158] == anchors[1152]).all()  # six anchors per location at stride 16
    assert anchors[-1] == pytest.approx((11.5 / 12, 11.5 / 12))


def test_decoding_places_boxes_and_keypoints_relative_to_anchors():
    anchors = g.ssd_anchors()
    boxes = np.zeros((1, 2016, 18), np.float32)
    scores = np.full((1, 2016, 1), -10.0, np.float32)
    boxes[0, 500, :4] = (19.2, -9.6, 38.4, 57.6)  # shift (+0.1, -0.05), size (0.2, 0.3)
    boxes[0, 500, 4:6] = (9.6, 9.6)
    scores[0, 500, 0] = 3.0
    palms = g.decode_palms(boxes, scores, anchors)
    assert len(palms) == 1
    palm = palms[0]
    ax, ay = anchors[500]
    assert palm.box == pytest.approx((ax + 0.1, ay - 0.05, 0.2, 0.3))
    assert palm.keypoints[0] == pytest.approx((ax + 0.05, ay + 0.05))
    assert palm.score == pytest.approx(1 / (1 + math.exp(-3.0)))


def test_weighted_nms_merges_overlaps_and_keeps_separate_hands():
    kp = np.zeros((7, 2))
    a = g.Palm(0.9, (0.50, 0.50, 0.2, 0.2), kp + 0.50)
    b = g.Palm(0.6, (0.52, 0.50, 0.2, 0.2), kp + 0.52)
    far = g.Palm(0.7, (0.10, 0.10, 0.1, 0.1), kp + 0.10)
    kept = g.weighted_nms([b, far, a])
    assert len(kept) == 2
    merged = kept[0]
    assert merged.score == 0.9
    assert merged.box[0] == pytest.approx((0.5 * 0.9 + 0.52 * 0.6) / 1.5)
    assert kept[1].box == pytest.approx(far.box)


def test_letterbox_and_its_removal():
    scale, new_w, new_h, left, top = g.letterbox(W, H)
    assert (new_w, new_h, left, top) == (192, 144, 0, 24)
    palm = g.Palm(1.0, (0.5, 0.125, 0.1, 0.075), np.array([[0.5, 0.875]] * 7))
    back = g.remove_letterbox(palm, W, H)
    assert back.box == pytest.approx((0.5, 0.0, 0.1, 0.1))
    assert back.keypoints[0] == pytest.approx((0.5, 1.0))


def _palm_from_points(wrist, middle_base):
    keypoints = np.zeros((7, 2))
    keypoints[0], keypoints[2] = wrist, middle_base
    return g.Palm(1.0, (wrist[0], (wrist[1] + middle_base[1]) / 2, 0.1, 0.1), keypoints)


def test_palm_rotation_upright_and_pointing_right():
    upright = g.palm_to_rect(_palm_from_points((0.5, 0.6), (0.5, 0.5)), W, H)
    assert upright.rotation == pytest.approx(0.0)
    assert upright.y_center < 0.55  # shifted towards the fingers
    right = g.palm_to_rect(_palm_from_points((0.4, 0.5), (0.5, 0.5)), W, H)
    assert right.rotation == pytest.approx(math.pi / 2)
    assert right.x_center == pytest.approx(0.4 + 0.5 * 0.1 * H / W)  # box centre shifted towards the fingers


def test_rects_are_square_in_pixels():
    rect = g.palm_to_rect(_palm_from_points((0.3, 0.7), (0.35, 0.6)), W, H)
    assert rect.width * W == pytest.approx(rect.height * H)


@pytest.mark.parametrize("angle", [-60, -20, 0, 25, 70])
@pytest.mark.parametrize("center", [(0.5, 0.5), (0.25, 0.7), (0.8, 0.3)])
def test_crop_then_projection_is_an_exact_round_trip(angle, center):
    hand = make_hand("open", center=center, angle_deg=angle, aspect=W / H)
    rect = g.landmarks_to_rect(hand.landmarks, W, H)
    matrix = g.crop_matrix(rect, W, H)
    pixels = np.c_[hand.landmarks[:, 0] * W, hand.landmarks[:, 1] * H, np.ones(21)]
    in_crop = pixels @ matrix.T
    crop_landmarks = np.c_[in_crop, np.zeros(21)]
    back = g.project_landmarks(crop_landmarks, rect)
    assert back[:, :2] == pytest.approx(hand.landmarks[:, :2], abs=1e-5)


@pytest.mark.parametrize("angle", [-70, -30, 0, 30, 70])
def test_the_hand_stands_upright_and_whole_in_its_crop(angle):
    hand = make_hand("open", center=(0.5, 0.55), size=0.2, angle_deg=angle, aspect=W / H)
    rect = g.landmarks_to_rect(hand.landmarks, W, H)
    matrix = g.crop_matrix(rect, W, H)
    pts = np.c_[hand.landmarks[:, 0] * W, hand.landmarks[:, 1] * H, np.ones(21)] @ matrix.T
    wrist, middle_base = pts[0], pts[9]
    assert middle_base[1] < wrist[1]  # fingers up
    assert abs(middle_base[0] - wrist[0]) < 0.25 * abs(middle_base[1] - wrist[1])
    stable = pts[list(g.STABLE_LANDMARKS)]
    assert (stable >= 0).all() and (stable <= g.HAND_INPUT).all()


def test_rect_iou():
    a = g.NormRect(0.5, 0.5, 0.2, 0.2)
    assert g.rect_iou(a, a) == pytest.approx(1.0)
    assert g.rect_iou(a, g.NormRect(0.9, 0.9, 0.1, 0.1)) == 0.0


def test_normalize_radians():
    assert g.normalize_radians(3 * math.pi / 2) == pytest.approx(-math.pi / 2)
    assert g.normalize_radians(-3 * math.pi / 2) == pytest.approx(math.pi / 2)
