from sanscontact.interpretation.hand_pose import features
from sanscontact.interpretation.lock import HandLock, preferred
from tests.synthetic.hand_model import make_hand

ASPECT = 4 / 3


def cand(**kwargs):
    hand = make_hand(**kwargs)
    return hand, features(hand, ASPECT)


def test_preferred_picks_the_closest_allowed_hand():
    near = cand(size=0.25, center=(0.7, 0.5), person_hand="right")
    far = cand(size=0.10, center=(0.3, 0.5), person_hand="left")
    assert preferred([far, near], "any") is near
    assert preferred([far, near], "left") is far
    assert preferred([far], "right") is None


def test_follows_the_engaged_hand_and_ignores_another_person():
    lock = HandLock()
    mine = cand(center=(0.5, 0.5))
    lock.engage(mine, t=0.0)
    other = cand(center=(0.9, 0.2), person_hand="right")
    moved = cand(center=(0.53, 0.52))
    assert lock.select([other, moved], t=0.033, aspect=ASPECT)[0] is moved[0]
    assert lock.select([other], t=0.066, aspect=ASPECT) is None


def test_rejects_wrong_side_and_wrong_size():
    lock = HandLock()
    lock.engage(cand(center=(0.5, 0.5), person_hand="left", size=0.18), t=0.0)
    assert lock.select([cand(center=(0.5, 0.5), person_hand="right")], t=0.03, aspect=ASPECT) is None
    assert lock.select([cand(center=(0.5, 0.5), size=0.40)], t=0.03, aspect=ASPECT) is None


def test_allowed_jump_grows_while_the_hand_is_missing():
    lock = HandLock(max_jump=0.1, jump_growth_per_s=0.5)
    lock.engage(cand(center=(0.4, 0.5)), t=0.0)
    far = cand(center=(0.6, 0.5))  # 0.27 in scaled units
    assert lock.select([far], t=0.03, aspect=ASPECT) is None
    assert lock.missing_for(0.5) == 0.5
    assert lock.select([far], t=0.5, aspect=ASPECT)[0] is far[0]
    assert lock.missing_for(0.5) == 0.0


def test_not_engaged_selects_nothing():
    lock = HandLock()
    assert not lock.engaged
    assert lock.select([cand()], t=0.0) is None
    assert lock.missing_for(10.0) == 0.0
