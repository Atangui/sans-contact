// Runs the demo engine (docs/demo/engine.js) on a JSON request read from stdin and prints the
// results as JSON. Used by tests/test_demo_engine.py to compare it with the Python code.
"use strict";

const path = require("path");
const E = require(path.join(__dirname, "..", "..", "docs", "demo", "engine.js"));

function poseDict(p) {
  return {
    size: p.size, center: p.center, extended: p.extended, spread_deg: p.spreadDeg,
    thumb_spread_deg: p.thumbSpreadDeg, pinch_index: p.pinchIndex, pinch_middle: p.pinchMiddle,
    tip_to_palm: p.tipToPalm, open_palm: p.openPalm, curled: p.curled, fist: p.fist,
    two_fingers: p.twoFingers(0.38),
  };
}

function frameDict(f) {
  return {
    state: f.state, freeze: f.freeze, rollback: f.rollback, events: f.events,
    actions: f.actions.map((a) => [a.action, a.amount]),
  };
}

function hands(request) {
  return request.hands.map((h) => {
    const options = {
      center: h.center, size: h.size, angleDeg: h.angle_deg, personHand: h.person_hand, aspect: h.aspect,
      pinch: h.pinch,
    };
    return E.makeHand(h.pose, options).landmarks.map((l) => l.slice(0, 2));
  });
}

function features(request) {
  const config = E.gestureConfig();
  return request.hands.map((h) => {
    const pose = E.features({ landmarks: h.landmarks, handedness: h.handedness }, request.aspect);
    return { ...poseDict(pose), intent: E.intent(pose, config) };
  });
}

// Same loop as the Python test: engagement in standby, then lock, gestures, pointer and dwell.
function session(request) {
  const aspect = request.aspect;
  const desktop = E.rect(...request.desktop);
  const screens = [desktop];
  const engagement = new E.EngagementDetector();
  const lock = new E.HandLock();
  const gestures = new E.GestureMachine(E.gestureConfig({ scrollSmooth: request.scroll_smooth }));
  const pointer = new E.Pointer(E.DEFAULT_ZONE, new E.OneEuroFilter2D(), request.pointer_mode, 1.0, 0.5, 0.1);
  const dwell = new E.DwellClicker();
  let active = false;
  const out = [];
  for (const frame of request.frames) {
    const t = frame.t;
    const candidates = frame.hands.map((h) => {
      const hand = { landmarks: h.landmarks, handedness: h.handedness };
      return [hand, E.features(hand, aspect)];
    });
    const row = { active };
    if (!active) {
      const candidate = E.preferred(candidates, "any");
      const engaged = engagement.update(candidate ? candidate[1] : null, t, aspect);
      row.engaged = engaged;
      row.progress = engagement.progress(t);
      if (engaged && candidate) {
        lock.engage(candidate, t);
        active = true;
        gestures.reset();
        dwell.reset();
        pointer.reset([0, 0]);
      }
      out.push(row);
      continue;
    }
    const selected = lock.select(candidates, t, aspect);
    row.selected = selected === null ? null : candidates.findIndex((c) => c[0] === selected[0]);
    if (selected === null) {
      row.gesture = frameDict(gestures.handMissing(t));
      if (lock.missingFor(t) > 3.0) {
        active = false;
        row.lost = true;
        engagement.reset();
        row.released = gestures.reset().map((a) => [a.action, a.amount]);
        lock.release();
      }
      out.push(row);
      continue;
    }
    const [hand, pose] = selected;
    const g = gestures.update(pose, t, aspect);
    row.gesture = frameDict(g);
    const [x, y] = E.referencePoint(hand, pose, request.pointer_landmark);
    const target = pointer.update(x, y, t, desktop, screens, g.freeze, g.rollback);
    row.cursor = target;
    row.dwell = dwell.update(target, t, g.state === E.State.POINT && !g.freeze);
    out.push(row);
  }
  return { frames: out, counts: gestures.counts };
}

function power(request) {
  const machine = new E.PowerMachine(request.pause_timeout_s);
  return request.ops.map(([op, arg, now]) => {
    const call = {
      activate: () => machine.activate(),
      deactivate: () => machine.deactivate(arg),
      toggle: () => machine.toggle(),
      engaged: () => machine.engaged(),
      hand_lost: () => machine.handLost(),
      pointer_taken: () => machine.pointerTaken(arg, now),
      tick: () => machine.tick(now),
    }[op];
    const transition = call();
    return {
      state: machine.state, reason: machine.reason, remaining: machine.pauseRemaining(now),
      transition: transition && [transition.previous, transition.state, transition.reason, transition.cameraStarted,
        transition.cameraStopped, transition.leftActive],
    };
  });
}

const HANDLERS = { hands, features, session, power };

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => { input += chunk; });
process.stdin.on("end", () => {
  const request = JSON.parse(input);
  process.stdout.write(JSON.stringify(HANDLERS[request.kind](request)));
});
