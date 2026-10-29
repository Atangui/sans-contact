/* SansContact demo engine: a line-by-line port of the Python code that interprets a hand.

   Sources (same names, same numbers, same order of operations):
   - tests/synthetic/hand_model.py          synthetic hands (21 points, no image)
   - src/sanscontact/interpretation/        hand_pose, gestures, engagement, one_euro, pointer, lock, dwell
   - src/sanscontact/power.py, geometry.py  on/off state machine, screen clamping

   Pure code: no DOM, no clock, no network. tests/test_demo_engine.py runs it under Node and
   checks it frame by frame against the Python modules. */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SansContactEngine = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // ---- perception/types.py ---------------------------------------------------------------------
  const WRIST = 0;
  const THUMB = [1, 2, 3, 4];
  const INDEX = [5, 6, 7, 8];
  const MIDDLE = [9, 10, 11, 12];
  const RING = [13, 14, 15, 16];
  const PINKY = [17, 18, 19, 20];
  const FINGERS = [INDEX, MIDDLE, RING, PINKY];
  const PALM = [0, 5, 9, 13, 17];
  const BONES = [
    [0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10], [10, 11], [11, 12],
    [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [0, 17], [17, 18], [18, 19], [19, 20],
  ];

  const f32 = Math.fround;
  const radians = (deg) => deg * (Math.PI / 180);
  const degrees = (rad) => rad * (180 / Math.PI);
  const norm = (x, y) => Math.sqrt(x * x + y * y); // numpy.linalg.norm: sqrt(dot(v, v))
  const hypot = Math.hypot;

  /** Python's round(): halves go to the even neighbour. */
  function roundHalfEven(x) {
    const r = Math.round(x);
    return Math.abs(x % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r;
  }

  // ---- tests/synthetic/hand_model.py -----------------------------------------------------------
  // Hand frame: wrist at the origin, fingers towards -y, unit = wrist-to-middle-base distance.
  // The template is a person's LEFT hand, palm towards a non-mirrored camera (thumb on the image left).
  const NAMES = ["index", "middle", "ring", "pinky"];
  const MCP = { index: [-0.30, -0.95], middle: [0.0, -1.0], ring: [0.27, -0.93], pinky: [0.50, -0.80] };
  const LENGTHS = {
    index: [0.45, 0.27, 0.22], middle: [0.50, 0.30, 0.23], ring: [0.46, 0.28, 0.22], pinky: [0.36, 0.22, 0.19],
  };
  const THUMB_CMC = [-0.35, -0.25];
  const THUMB_LENGTHS = [0.32, 0.27, 0.24];

  const SPREAD_OPEN = { index: -14.0, middle: 0.0, ring: 12.0, pinky: 26.0 };
  const SPREAD_TOGETHER = { index: -4.0, middle: 0.0, ring: 3.0, pinky: 7.0 };
  const CURLED = [85.0, 95.0, 60.0];
  const STRAIGHT = [0.0, 0.0, 0.0];
  const BENT = [25.0, 35.0, 20.0];
  const SPREAD_PINCH_MIDDLE = { index: -22.0, middle: 0.0, ring: 3.0, pinky: 7.0 };

  const POSES = {
    // name: [spread, {finger: flex}, thumb_angle, thumb_flex]
    open: [SPREAD_OPEN, {}, -60.0, STRAIGHT],
    relaxed: [SPREAD_TOGETHER, {}, -25.0, [20.0, 30.0, 20.0]],
    fist: [SPREAD_TOGETHER, { index: CURLED, middle: CURLED, ring: CURLED, pinky: CURLED }, 35.0, [20.0, 40.0, 30.0]],
    point: [SPREAD_TOGETHER, { middle: CURLED, ring: CURLED, pinky: CURLED }, -20.0, [40.0, 60.0, 50.0]],
    two_fingers: [{ index: -6.0, middle: 6.0, ring: 3.0, pinky: 7.0 }, { ring: CURLED, pinky: CURLED }, 30.0,
      [20.0, 40.0, 30.0]],
    pinch_index: [SPREAD_TOGETHER, { index: BENT }, -45.0, STRAIGHT],
    pinch_middle: [SPREAD_PINCH_MIDDLE, { middle: BENT }, -45.0, STRAIGHT],
  };
  const PINCH_TARGET = { pinch_index: 8, pinch_middle: 12 };
  const PINCH_GAP = 0.03;

  function chain(base, directionDeg, lengths, flex) {
    const points = [];
    let [x, y] = base;
    const angle = radians(directionDeg);
    let cumulative = 0.0;
    for (let i = 0; i < lengths.length; i++) {
      cumulative += radians(flex[i]);
      const projected = lengths[i] * Math.cos(cumulative);
      x += projected * Math.sin(angle);
      y -= projected * Math.cos(angle);
      points.push([x, y]);
    }
    return points;
  }

  /** 21 [x, y] points in the hand frame. For the pinch postures, pinch goes from 0 (away) to 1 (touching). */
  function handPoints(pose, pinch = 1.0) {
    const [spread, flexes, thumbAngle, thumbFlex] = POSES[pose];
    const points = Array.from({ length: 21 }, () => [0, 0]);
    const thumb = chain(THUMB_CMC, thumbAngle, THUMB_LENGTHS, thumbFlex);
    points[1] = THUMB_CMC.slice();
    points[2] = thumb[0];
    points[3] = thumb[1];
    points[4] = thumb[2];
    NAMES.forEach((finger, i) => {
      const base = 5 + 4 * i;
      points[base] = MCP[finger].slice();
      const flex = flexes[finger] || STRAIGHT;
      chain(MCP[finger], spread[finger], LENGTHS[finger], flex).forEach((p, k) => { points[base + 1 + k] = p; });
    });
    if (pose in PINCH_TARGET) {
      const target = points[PINCH_TARGET[pose]];
      const cmc = THUMB_CMC;
      const d = norm(target[0] - cmc[0], target[1] - cmc[1]);
      const direction = [(target[0] - cmc[0]) / d, (target[1] - cmc[1]) / d];
      const touching = [target[0] - direction[0] * PINCH_GAP, target[1] - direction[1] * PINCH_GAP];
      const tip = [points[4][0] + (touching[0] - points[4][0]) * pinch, points[4][1] + (touching[1] - points[4][1]) * pinch];
      const normal = [-(tip[1] - cmc[1]), tip[0] - cmc[0]];
      const n = Math.max(norm(normal[0], normal[1]), 1e-9);
      const bulge = [(0.08 * normal[0]) / n, (0.08 * normal[1]) / n];
      points[2] = [cmc[0] + (tip[0] - cmc[0]) * 0.40 - bulge[0], cmc[1] + (tip[1] - cmc[1]) * 0.40 - bulge[1]];
      points[3] = [cmc[0] + (tip[0] - cmc[0]) * 0.72 - bulge[0] * 0.6, cmc[1] + (tip[1] - cmc[1]) * 0.72 - bulge[1] * 0.6];
      points[4] = tip;
    }
    return points;
  }

  /** Linear blend of two hand-frame shapes (the demo animates postures this way). */
  function blendPoints(a, b, k) {
    return a.map((p, i) => [p[0] + (b[i][0] - p[0]) * k, p[1] + (b[i][1] - p[1]) * k]);
  }

  /** make_hand() from hand-frame points: scale, side, rotation, placement, float32 landmarks. */
  function placeHand(handFramePoints, { center = [0.5, 0.55], size = 0.18, angleDeg = 0.0, personHand = "left",
    aspect = 4 / 3, score = 0.95 } = {}) {
    let points = handFramePoints.map(([x, y]) => [x * size, y * size]);
    if (personHand === "right") points = points.map(([x, y]) => [x * -1, y]);
    const a = radians(angleDeg);
    const c = Math.cos(a);
    const s = Math.sin(a);
    points = points.map(([x, y]) => [x * c + y * -s, x * s + y * c]);
    let px = 0;
    let py = 0;
    for (const i of PALM) { px += points[i][0]; py += points[i][1]; }
    const offset = [center[0] * aspect - px / PALM.length, center[1] - py / PALM.length];
    const landmarks = points.map(([x, y]) => [f32((x + offset[0]) / aspect), f32(y + offset[1]), 0]);
    const handedness = personHand === "left" ? "Right" : "Left"; // models label as if mirrored
    return { landmarks, handedness, score };
  }

  function makeHand(pose = "open", options = {}) {
    return placeHand(handPoints(pose, options.pinch === undefined ? 1.0 : options.pinch), options);
  }

  // ---- interpretation/hand_pose.py -------------------------------------------------------------
  const STRAIGHT_FINGER = 0.88;
  const STRAIGHT_THUMB = 0.85;
  const THUMB_AWAY = 0.55;
  const OPEN_SPREAD_SUM_DEG = 24.0;
  const OPEN_EDGE_SPREAD_DEG = 5.0;
  const OPEN_THUMB_CLEAR = 0.45;
  const CURLED_TIP = 0.55;

  class PoseFeatures {
    constructor(f) { Object.assign(this, f); Object.freeze(this); }

    get openPalm() {
      const [indexMid, , ringPinky] = this.spreadDeg;
      return this.extended.slice(1).every(Boolean)
        && this.spreadDeg[0] + this.spreadDeg[1] + this.spreadDeg[2] >= OPEN_SPREAD_SUM_DEG
        && Math.min(indexMid, ringPinky) >= OPEN_EDGE_SPREAD_DEG
        && this.pinchIndex > OPEN_THUMB_CLEAR;
    }

    /** Index, middle, ring, pinky folded into the palm. */
    get curled() { return this.tipToPalm.map((d) => d < CURLED_TIP); }

    get fist() { return this.curled.every(Boolean); }

    /** Index and middle straight, ring and pinky folded, thumb away from both tips. */
    twoFingers(thumbAway) {
      const [, index, middle] = this.extended;
      const curled = this.curled;
      return index && middle && curled[2] && curled[3] && Math.min(this.pinchIndex, this.pinchMiddle) > thumbAway;
    }
  }

  const sub = (p, q) => [p[0] - q[0], p[1] - q[1]];
  const dist = (p, q) => norm(p[0] - q[0], p[1] - q[1]);

  function scaledPoints(landmarks, aspect) {
    return landmarks.map((l) => [l[0] * aspect, l[1]]);
  }

  function handSize(points) {
    let size = dist(points[MIDDLE[0]], points[WRIST]);
    if (size < 1e-6) {
      size = PALM.slice(1).reduce((acc, i) => acc + dist(points[i], points[WRIST]), 0) / (PALM.length - 1);
    }
    return Math.max(size, 1e-6);
  }

  function straightness(points, chainIdx) {
    let segments = 0;
    for (let i = 1; i < chainIdx.length; i++) segments += dist(points[chainIdx[i]], points[chainIdx[i - 1]]);
    if (segments < 1e-9) return 0.0;
    return dist(points[chainIdx[chainIdx.length - 1]], points[chainIdx[0]]) / segments;
  }

  function angleDeg(u, v) {
    const nu = norm(u[0], u[1]);
    const nv = norm(v[0], v[1]);
    if (nu < 1e-9 || nv < 1e-9) return 0.0;
    const cos = Math.min(Math.max((u[0] * v[0] + u[1] * v[1]) / (nu * nv), -1.0), 1.0);
    return degrees(Math.acos(cos));
  }

  function fingerExtended(points, finger) {
    const [, pip, , tip] = finger;
    const wrist = points[WRIST];
    const farther = dist(points[tip], wrist) > dist(points[pip], wrist);
    return farther && straightness(points, finger) >= STRAIGHT_FINGER;
  }

  function thumbExtended(points, size) {
    const away = dist(points[THUMB[3]], points[INDEX[0]]) / size >= THUMB_AWAY;
    return away && straightness(points, THUMB.slice(1)) >= STRAIGHT_THUMB;
  }

  /** Palm centre in normalised image coordinates, as numpy computes a float32 mean. */
  function float32PalmCenter(landmarks) {
    let sx = f32(0);
    let sy = f32(0);
    for (const i of PALM) { sx = f32(sx + landmarks[i][0]); sy = f32(sy + landmarks[i][1]); }
    return [f32(sx / PALM.length), f32(sy / PALM.length)];
  }

  function features(hand, aspect) {
    const points = scaledPoints(hand.landmarks, aspect);
    const size = handSize(points);
    const directions = FINGERS.map((f) => sub(points[f[3]], points[f[0]]));
    const spread = [0, 1, 2].map((i) => angleDeg(directions[i], directions[i + 1]));
    const thumbDir = sub(points[THUMB[3]], points[THUMB[1]]);
    const center = float32PalmCenter(hand.landmarks);
    let palmX = 0;
    let palmY = 0;
    for (const i of PALM) { palmX += points[i][0]; palmY += points[i][1]; }
    const palm = [palmX / PALM.length, palmY / PALM.length];
    const thumbTip = points[THUMB[3]];
    return new PoseFeatures({
      size,
      center,
      extended: [thumbExtended(points, size), ...FINGERS.map((f) => fingerExtended(points, f))],
      spreadDeg: spread,
      thumbSpreadDeg: angleDeg(thumbDir, directions[0]),
      pinchIndex: dist(thumbTip, points[INDEX[3]]) / size,
      pinchMiddle: dist(thumbTip, points[MIDDLE[3]]) / size,
      tipToPalm: FINGERS.map((f) => dist(points[f[3]], palm) / size),
    });
  }

  /** Hand models label hands as if the frame were mirrored; our frames are not, so the label is swapped. */
  function personHand(label) {
    return { Left: "right", Right: "left" }[label] || "unknown";
  }

  // ---- interpretation/gestures.py --------------------------------------------------------------
  const WHEEL_DELTA = 120;
  const State = Object.freeze({
    POINT: "point", CLUTCH: "clutch", LEFT_PENDING: "left_pending", LEFT_DOWN: "left_down", DRAG: "drag",
    RIGHT_PENDING: "right_pending", RIGHT_DOWN: "right_down", SCROLL: "scroll",
  });
  const Action = Object.freeze({
    LEFT_DOWN: "left_down", LEFT_UP: "left_up", RIGHT_DOWN: "right_down", RIGHT_UP: "right_up",
    WHEEL: "wheel", HWHEEL: "hwheel",
  });
  const mouseAction = (action, amount = 0) => Object.freeze({ action, amount });

  const DEFAULT_GESTURES = Object.freeze({
    press: 0.25,
    release: 0.38,
    minPressS: 0.06,
    dragStart: 0.35,
    doubleClickS: 0.5,
    doubleClickMove: 0.4,
    postureFrames: 2,
    scrollDeadZone: 0.10,
    scrollSpeed: 12.0,
    scrollSmooth: true,
    scrollInvert: false,
    lostReleaseS: 0.25,
  });

  function gestureConfig(overrides = {}) {
    const config = Object.freeze({ ...DEFAULT_GESTURES, ...overrides });
    if (!(config.press > 0 && config.press < config.release)) {
      throw new RangeError("pinch thresholds must satisfy 0 < press < release");
    }
    return config;
  }

  /** Which gesture a single posture asks for, before any timing: the coherence rules. */
  function intent(pose, config) {
    if (pose.fist) return "clutch";
    if (pose.pinchIndex < config.press && pose.pinchMiddle >= config.press && !pose.curled[0]) return "left";
    if (pose.pinchMiddle < config.press && pose.pinchIndex > config.release && !pose.curled[1]) return "right";
    if (pose.twoFingers(config.release)) return "scroll";
    return "point";
  }

  const newContext = (since = 0.0, anchor = [0.0, 0.0]) => ({ since, anchor, frames: 0, scrollAcc: [0.0, 0.0] });

  function travel(anchor, pose, aspect) {
    return hypot((pose.center[0] - anchor[0]) * aspect, pose.center[1] - anchor[1]) / pose.size;
  }

  class GestureMachine {
    constructor(config = gestureConfig()) {
      this.config = config;
      this.state = State.POINT;
      this.ctx = newContext();
      this.fistFrames = 0;
      this.twoFrames = 0;
      this.lastT = null;
      this.lastSeen = null;
      this.freezeUntil = 0.0;
      this.freezeAnchor = [0.0, 0.0];
      this.lastClickT = -Infinity;
      this.counts = { click: 0, double_click: 0, right_click: 0, drag: 0, scroll: 0, clutch: 0, ignored: 0 };
    }

    update(pose, t, aspect = 4 / 3) {
      const dt = this.lastT === null ? 0.0 : Math.max(0.0, t - this.lastT);
      this.lastT = t;
      this.lastSeen = t;
      this.fistFrames = pose.fist ? this.fistFrames + 1 : 0;
      this.twoFrames = pose.twoFingers(this.config.release) ? this.twoFrames + 1 : 0;
      const frame = this.handlers[this.state].call(this, pose, t, dt, aspect);
      for (const event of frame.events) if (event in this.counts) this.counts[event] += 1;
      return frame;
    }

    /** No hand this frame. Buttons are released if it lasts more than lostReleaseS. */
    handMissing(t) {
      this.lastT = t;
      if (this.lastSeen !== null && t - this.lastSeen >= this.config.lostReleaseS) {
        const actions = this.reset();
        return makeFrame(State.POINT, false, false, actions, actions.length ? ["lost"] : []);
      }
      return makeFrame(this.state, this.state !== State.DRAG);
    }

    /** Back to POINT; returns the button releases needed so nothing stays pressed. */
    reset() {
      const actions = this.releases();
      this.state = State.POINT;
      this.ctx = newContext();
      this.fistFrames = 0;
      this.twoFrames = 0;
      this.freezeUntil = 0.0;
      return actions;
    }

    onPoint(pose, t, dt, aspect) {
      const c = this.config;
      let frozen = t < this.freezeUntil;
      if (frozen && travel(this.freezeAnchor, pose, aspect) > c.doubleClickMove) {
        this.freezeUntil = 0.0;
        frozen = false;
      }
      const wanted = intent(pose, c);
      if (wanted === "clutch" && this.fistFrames >= c.postureFrames) {
        return this.go(State.CLUTCH, pose, t, true, false, [], ["clutch"]);
      }
      if (wanted === "left") return this.go(State.LEFT_PENDING, pose, t, true, !frozen);
      if (wanted === "right") return this.go(State.RIGHT_PENDING, pose, t, true, !frozen);
      if (wanted === "scroll" && this.twoFrames >= c.postureFrames) {
        return this.go(State.SCROLL, pose, t, true, false, [], ["scroll"]);
      }
      return this.frame(frozen, pose);
    }

    onLeftPending(pose, t) {
      const c = this.config;
      if (pose.fist || pose.pinchIndex > c.release) return this.go(State.POINT, pose, t, false, false, [], ["ignored"]);
      if (t - this.ctx.since >= c.minPressS) {
        this.state = State.LEFT_DOWN;
        return this.frame(true, pose, false, [mouseAction(Action.LEFT_DOWN)]);
      }
      return this.frame(true, pose);
    }

    onLeftDown(pose, t, dt, aspect) {
      const c = this.config;
      if (pose.pinchIndex > c.release) {
        const double = t - this.lastClickT <= c.doubleClickS;
        this.lastClickT = double ? -Infinity : t;
        // Keep the cursor still where the pinch started, so a second pinch is a valid double click.
        this.freezeUntil = t + c.doubleClickS;
        this.freezeAnchor = this.ctx.anchor;
        return this.go(State.POINT, pose, t, true, false, [mouseAction(Action.LEFT_UP)],
          double ? ["click", "double_click"] : ["click"]);
      }
      if (travel(this.ctx.anchor, pose, aspect) > c.dragStart) {
        this.state = State.DRAG;
        return this.frame(false, pose, false, [], ["drag"]);
      }
      return this.frame(true, pose);
    }

    onDrag(pose, t) {
      if (pose.pinchIndex > this.config.release) {
        return this.go(State.POINT, pose, t, false, false, [mouseAction(Action.LEFT_UP)], ["drop"]);
      }
      return this.frame(false, pose);
    }

    onRightPending(pose, t) {
      const c = this.config;
      if (pose.fist || pose.pinchMiddle > c.release || pose.pinchIndex < c.press) {
        return this.go(State.POINT, pose, t, false, false, [], ["ignored"]);
      }
      if (t - this.ctx.since >= c.minPressS) {
        this.state = State.RIGHT_DOWN;
        return this.frame(true, pose, false, [mouseAction(Action.RIGHT_DOWN)]);
      }
      return this.frame(true, pose);
    }

    onRightDown(pose, t) {
      if (pose.pinchMiddle > this.config.release) {
        return this.go(State.POINT, pose, t, false, false, [mouseAction(Action.RIGHT_UP)], ["right_click"]);
      }
      return this.frame(true, pose);
    }

    onScroll(pose, t, dt, aspect) {
      const c = this.config;
      if (this.twoFrames === 0) {
        this.ctx.frames += 1;
        if (this.ctx.frames >= c.postureFrames) return this.go(State.POINT, pose, t, false);
        return this.frame(true, pose);
      }
      this.ctx.frames = 0;
      // Mirrored view: the hand moving right on screen means x decreasing in the image.
      const offsetX = (-(pose.center[0] - this.ctx.anchor[0]) * aspect) / pose.size;
      const offsetY = -(pose.center[1] - this.ctx.anchor[1]) / pose.size;
      const actions = [];
      for (const [axis, offset, kind] of [[0, offsetX, Action.HWHEEL], [1, offsetY, Action.WHEEL]]) {
        const excess = Math.max(0.0, Math.abs(offset) - c.scrollDeadZone);
        let velocity = excess ? excess * c.scrollSpeed * WHEEL_DELTA * copysignOne(offset) : 0.0;
        if (c.scrollInvert) velocity = -velocity;
        this.ctx.scrollAcc[axis] += velocity * dt;
        const step = c.scrollSmooth ? 1 : WHEEL_DELTA;
        const amount = Math.trunc(this.ctx.scrollAcc[axis] / step) * step;
        if (amount) {
          this.ctx.scrollAcc[axis] -= amount;
          actions.push(mouseAction(kind, amount));
        }
      }
      return this.frame(true, pose, false, actions);
    }

    onClutch(pose, t) {
      if (this.fistFrames === 0) {
        this.ctx.frames += 1;
        if (this.ctx.frames >= this.config.postureFrames) return this.go(State.POINT, pose, t, false);
      } else {
        this.ctx.frames = 0;
      }
      return this.frame(true, pose);
    }

    go(state, pose, t, freeze, rollback = false, actions = [], events = []) {
      this.state = state;
      this.ctx = newContext(t, pose.center);
      return this.frame(freeze, pose, rollback, actions, events);
    }

    frame(freeze, pose, rollback = false, actions = [], events = []) {
      return makeFrame(this.state, freeze, rollback, actions, events, pose.pinchIndex, pose.pinchMiddle);
    }

    releases() {
      if (this.state === State.LEFT_DOWN || this.state === State.DRAG) return [mouseAction(Action.LEFT_UP)];
      if (this.state === State.RIGHT_DOWN) return [mouseAction(Action.RIGHT_UP)];
      return [];
    }
  }

  GestureMachine.prototype.handlers = {
    [State.POINT]: GestureMachine.prototype.onPoint,
    [State.CLUTCH]: GestureMachine.prototype.onClutch,
    [State.LEFT_PENDING]: GestureMachine.prototype.onLeftPending,
    [State.LEFT_DOWN]: GestureMachine.prototype.onLeftDown,
    [State.DRAG]: GestureMachine.prototype.onDrag,
    [State.RIGHT_PENDING]: GestureMachine.prototype.onRightPending,
    [State.RIGHT_DOWN]: GestureMachine.prototype.onRightDown,
    [State.SCROLL]: GestureMachine.prototype.onScroll,
  };

  /** math.copysign(1.0, x): the sign of x, -0.0 included. */
  function copysignOne(x) {
    return x < 0 || Object.is(x, -0) ? -1 : 1;
  }

  function makeFrame(state, freeze, rollback = false, actions = [], events = [], pinchIndex = 1.0, pinchMiddle = 1.0) {
    return Object.freeze({ state, freeze, rollback, actions, events, pinchIndex, pinchMiddle });
  }

  // ---- interpretation/engagement.py ------------------------------------------------------------
  /** Engagement gesture: open palm, fingers spread, held still for about one second. */
  class EngagementDetector {
    constructor(holdS = 1.0, maxMotion = 0.35, graceFrames = 2) {
      this.holdS = holdS;
      this.maxMotion = maxMotion;
      this.graceFrames = graceFrames;
      this.reset();
    }

    reset() {
      this.start = null;
      this.anchor = null;
      this.misses = 0;
      this.armed = true;
    }

    progress(t) {
      if (this.start === null) return 0.0;
      return Math.min(1.0, (t - this.start) / this.holdS);
    }

    /** Feed one frame; returns true once, when the gesture completes. */
    update(pose, t, aspect = 4 / 3) {
      if (pose === null || !pose.openPalm) {
        this.misses += 1;
        if (this.misses > this.graceFrames) {
          this.start = null;
          this.anchor = null;
          this.armed = true;
        }
        return false;
      }
      this.misses = 0;
      if (!this.armed) return false;
      if (this.start === null || this.anchor === null) {
        this.start = t;
        this.anchor = pose.center;
        return false;
      }
      const drift = hypot((pose.center[0] - this.anchor[0]) * aspect, pose.center[1] - this.anchor[1]);
      if (drift / pose.size > this.maxMotion) {
        this.start = t;
        this.anchor = pose.center;
        return false;
      }
      if (t - this.start >= this.holdS) {
        this.start = null;
        this.anchor = null;
        this.armed = false;
        return true;
      }
      return false;
    }
  }

  // ---- interpretation/one_euro.py --------------------------------------------------------------
  function alpha(cutoffHz, dt) {
    const tau = 1.0 / (2.0 * Math.PI * cutoffHz);
    return 1.0 / (1.0 + tau / dt);
  }

  /** One Euro filter (Casiez, Roussel, Vogel, CHI 2012): steady at rest, responsive in motion. */
  class OneEuroFilter2D {
    constructor(minCutoff = 1.0, beta = 0.015, dCutoff = 1.0) {
      if (minCutoff <= 0 || dCutoff <= 0 || beta < 0) throw new RangeError("invalid One Euro parameters");
      this.minCutoff = minCutoff;
      this.beta = beta;
      this.dCutoff = dCutoff;
      this.reset();
    }

    reset() {
      this.t = null;
      this.x = [0.0, 0.0];
      this.dx = [0.0, 0.0];
    }

    filter(x, y, t) {
      if (this.t === null) {
        this.t = t;
        this.x = [x, y];
        this.dx = [0.0, 0.0];
        return this.x;
      }
      const dt = t - this.t;
      if (dt <= 0) return this.x;
      this.t = t;
      const [px, py] = this.x;
      const rawDx = [(x - px) / dt, (y - py) / dt];
      const aD = alpha(this.dCutoff, dt);
      const dx = [aD * rawDx[0] + (1 - aD) * this.dx[0], aD * rawDx[1] + (1 - aD) * this.dx[1]];
      const speed = hypot(dx[0], dx[1]);
      const a = alpha(this.minCutoff + this.beta * speed, dt);
      this.x = [a * x + (1 - a) * px, a * y + (1 - a) * py];
      this.dx = dx;
      return this.x;
    }
  }

  // ---- geometry.py -----------------------------------------------------------------------------
  /** Half-open rectangle: right and bottom are excluded, as in Win32 RECT. */
  function rect(left, top, right, bottom) {
    return Object.freeze({ left, top, right, bottom, width: right - left, height: bottom - top });
  }

  function clampToScreens(x, y, screens) {
    let best = null;
    let bestD = Infinity;
    for (const s of screens) {
      const cx = Math.min(Math.max(x, s.left), s.right - 1);
      const cy = Math.min(Math.max(y, s.top), s.bottom - 1);
      const d = (cx - x) ** 2 + (cy - y) ** 2;
      if (d < bestD) { best = [cx, cy]; bestD = d; }
    }
    if (best === null) throw new RangeError("no screen");
    return [roundHalfEven(best[0]), roundHalfEven(best[1])];
  }

  // ---- interpretation/pointer.py ---------------------------------------------------------------
  const DEFAULT_ZONE = Object.freeze({ x0: 0.2, y0: 0.15, x1: 0.8, y1: 0.75 });
  const HISTORY = 60;

  function toZone(x, y, zone, mirror = true) {
    if (mirror) x = 1.0 - x;
    const u = (x - zone.x0) / (zone.x1 - zone.x0);
    const v = (y - zone.y0) / (zone.y1 - zone.y0);
    return [Math.min(Math.max(u, 0.0), 1.0), Math.min(Math.max(v, 0.0), 1.0)];
  }

  function zoneToDesktop(u, v, desktop) {
    return [desktop.left + u * (desktop.width - 1), desktop.top + v * (desktop.height - 1)];
  }

  /** Inverse of toZone + zoneToDesktop: where the palm must be for the cursor to rest on (px, py). */
  function imagePointFor(px, py, desktop, zone = DEFAULT_ZONE) {
    const u = (px - desktop.left) / (desktop.width - 1);
    const v = (py - desktop.top) / (desktop.height - 1);
    return [1.0 - (zone.x0 + u * (zone.x1 - zone.x0)), zone.y0 + v * (zone.y1 - zone.y0)];
  }

  /** A stable point: palm centre or index base, never the fingertip (it moves when pinching). */
  function referencePoint(hand, pose, mode) {
    if (mode === "index_mcp") return [hand.landmarks[INDEX[0]][0], hand.landmarks[INDEX[0]][1]];
    return pose.center;
  }

  /** Where the cursor should be: mapping, smoothing, freezing, absolute or relative mode. */
  class Pointer {
    constructor(zone = DEFAULT_ZONE, smoothing = new OneEuroFilter2D(), mode = "absolute", relativeGain = 1.0,
      relativeAccel = 0.5, rollbackS = 0.1) {
      if (mode !== "absolute" && mode !== "relative") throw new RangeError(`unknown pointer mode ${mode}`);
      this.zone = zone;
      this.smoothing = smoothing;
      this.mode = mode;
      this.relativeGain = relativeGain;
      this.relativeAccel = relativeAccel;
      this.rollbackS = rollbackS;
      this.reset();
    }

    reset(cursor = null) {
      this.smoothing.reset();
      this.history = [];
      this.frozenAt = null;
      this.cursor = cursor === null ? null : [cursor[0], cursor[1]];
      this.previous = null;
    }

    get frozen() { return this.frozenAt !== null; }

    update(x, y, t, desktop, screens, freeze = false, rollback = false) {
      const [u, v] = toZone(x, y, this.zone);
      const [dx0, dy0] = zoneToDesktop(u, v, desktop);
      const [fx, fy] = this.smoothing.filter(dx0, dy0, t);
      let wanted;
      if (this.mode === "absolute" || this.cursor === null) {
        wanted = [fx, fy];
      } else {
        const [pt, px, py] = this.previous ? this.previous : [t, fx, fy];
        const dx = fx - px;
        const dy = fy - py;
        const dt = Math.max(t - pt, 1e-3);
        const speed = hypot(dx, dy) / dt;
        const gain = this.relativeGain * (1.0 + this.relativeAccel * Math.min(speed / 1000.0, 3.0));
        wanted = [this.cursor[0] + dx * gain, this.cursor[1] + dy * gain];
      }
      this.previous = [t, fx, fy];
      let target;
      if (freeze) {
        if (this.frozenAt === null) {
          this.frozenAt = rollback ? this.positionBefore(t) : this.current(wanted, screens);
        }
        target = this.frozenAt;
      } else {
        this.frozenAt = null;
        target = clampToScreens(wanted[0], wanted[1], screens);
      }
      this.cursor = [target[0], target[1]];
      this.history.push([t, target[0], target[1]]);
      if (this.history.length > HISTORY) this.history.shift();
      return target;
    }

    current(wanted, screens) {
      if (this.history.length) {
        const last = this.history[this.history.length - 1];
        return [last[1], last[2]];
      }
      return clampToScreens(wanted[0], wanted[1], screens);
    }

    positionBefore(t) {
      const targetTime = t - this.rollbackS;
      let best = null;
      for (const [when, x, y] of this.history) {
        if (when <= targetTime) best = [x, y];
        else break;
      }
      if (best === null && this.history.length) best = [this.history[0][1], this.history[0][2]];
      if (best === null) throw new RangeError("no position yet");
      return best;
    }
  }

  // ---- interpretation/lock.py ------------------------------------------------------------------
  /** Before engagement: the allowed hand closest to the camera (largest). */
  function preferred(candidates, handPref) {
    let best = null;
    for (const c of candidates) {
      if (handPref !== "any" && personHand(c[0].handedness) !== handPref) continue;
      if (best === null || c[1].size > best[1].size) best = c;
    }
    return best;
  }

  /** Only the person who made the engagement gesture controls the cursor. */
  class HandLock {
    constructor(maxJump = 0.25, jumpGrowthPerS = 0.5, sizeRatio = [0.6, 1.6]) {
      this.maxJump = maxJump;
      this.jumpGrowthPerS = jumpGrowthPerS;
      this.sizeRatio = sizeRatio;
      this.release();
    }

    get engaged() { return this.side !== null; }

    engage(candidate, t) {
      const [hand, pose] = candidate;
      this.side = personHand(hand.handedness);
      this.center = pose.center;
      this.size = pose.size;
      this.seenAt = t;
    }

    release() {
      this.side = null;
      this.center = [0.0, 0.0];
      this.size = 0.0;
      this.seenAt = 0.0;
    }

    missingFor(t) { return this.engaged ? t - this.seenAt : 0.0; }

    select(candidates, t, aspect = 4 / 3) {
      if (!this.engaged) return null;
      const allowedJump = this.maxJump + this.jumpGrowthPerS * Math.max(0.0, t - this.seenAt);
      let best = null;
      let bestD = Infinity;
      for (const [hand, pose] of candidates) {
        const side = personHand(hand.handedness);
        if (side !== this.side && side !== "unknown" && this.side !== "unknown") continue;
        const ratio = this.size ? pose.size / this.size : 1.0;
        if (!(this.sizeRatio[0] <= ratio && ratio <= this.sizeRatio[1])) continue;
        const d = hypot((pose.center[0] - this.center[0]) * aspect, pose.center[1] - this.center[1]);
        if (d <= allowedJump && d < bestD) { best = [hand, pose]; bestD = d; }
      }
      if (best !== null) {
        this.center = best[1].center;
        this.size = best[1].size;
        this.seenAt = t;
      }
      return best;
    }
  }

  // ---- interpretation/dwell.py -----------------------------------------------------------------
  /** Click by dwelling: keep the cursor still for a moment to click (off by default). */
  class DwellClicker {
    constructor(dwellS = 1.0, radiusPx = 12.0, rearmPx = 30.0) {
      this.dwellS = dwellS;
      this.radiusPx = radiusPx;
      this.rearmPx = rearmPx;
      this.reset();
    }

    reset() {
      this.anchor = null;
      this.since = 0.0;
      this.lastClick = null;
    }

    progress(t) {
      if (this.anchor === null || this.lastClick !== null) return 0.0;
      return Math.min(1.0, (t - this.since) / this.dwellS);
    }

    update(position, t, allowed) {
      if (!allowed || position === null) {
        this.anchor = null;
        return false;
      }
      if (this.lastClick !== null && dist(position, this.lastClick) > this.rearmPx) this.lastClick = null;
      if (this.anchor === null || dist(position, this.anchor) > this.radiusPx) {
        this.anchor = position;
        this.since = t;
        return false;
      }
      if (this.lastClick === null && t - this.since >= this.dwellS) {
        this.lastClick = this.anchor;
        this.anchor = null;
        return true;
      }
      return false;
    }
  }

  // ---- power.py --------------------------------------------------------------------------------
  const PowerState = Object.freeze({ OFF: "off", STANDBY: "standby", ACTIVE: "active", PAUSED: "paused" });
  const Reason = Object.freeze({
    STARTUP: "startup", USER: "user", ENGAGED: "engaged", HAND_LOST: "hand_lost", PHYSICAL_MOUSE: "physical_mouse",
    ELEVATED_WINDOW: "elevated_window", SECURE_DESKTOP: "secure_desktop", PAUSE_TIMEOUT: "pause_timeout",
    SESSION_LOCKED: "session_locked", ERROR: "error",
  });
  const PAUSE_REASONS = new Set([Reason.PHYSICAL_MOUSE, Reason.ELEVATED_WINDOW, Reason.SECURE_DESKTOP]);

  /** Explicit four-state machine. Every method returns the transition it made, or null. */
  class PowerMachine {
    constructor(pauseTimeoutS = 30.0) {
      if (pauseTimeoutS <= 0) throw new RangeError("pause_timeout_s must be positive");
      this.pauseTimeoutS = pauseTimeoutS;
      this.state = PowerState.OFF;
      this.reason = Reason.STARTUP;
      this.pausedAt = null;
    }

    get cameraOn() { return this.state !== PowerState.OFF; }

    get controlsCursor() { return this.state === PowerState.ACTIVE; }

    activate() { return this.state === PowerState.OFF ? this.go(PowerState.STANDBY, Reason.USER) : null; }

    deactivate(reason = Reason.USER) { return this.state === PowerState.OFF ? null : this.go(PowerState.OFF, reason); }

    toggle() { return this.state === PowerState.OFF ? this.activate() : this.deactivate(Reason.USER); }

    engaged() {
      if (this.state !== PowerState.STANDBY && this.state !== PowerState.PAUSED) return null;
      return this.go(PowerState.ACTIVE, Reason.ENGAGED);
    }

    handLost() { return this.state === PowerState.ACTIVE ? this.go(PowerState.STANDBY, Reason.HAND_LOST) : null; }

    pointerTaken(reason, now) {
      if (!PAUSE_REASONS.has(reason)) throw new RangeError(`${reason} is not a pause reason`);
      if (this.state !== PowerState.ACTIVE) return null;
      const transition = this.go(PowerState.PAUSED, reason);
      this.pausedAt = now;
      return transition;
    }

    /** Release the camera once the pause has lasted pauseTimeoutS. */
    tick(now) {
      const remaining = this.pauseRemaining(now);
      if (remaining !== null && remaining <= 0) return this.go(PowerState.OFF, Reason.PAUSE_TIMEOUT);
      return null;
    }

    pauseRemaining(now) {
      if (this.state !== PowerState.PAUSED || this.pausedAt === null) return null;
      return this.pauseTimeoutS - (now - this.pausedAt);
    }

    go(state, reason) {
      const transition = Object.freeze({
        previous: this.state, state, reason,
        get cameraStarted() { return this.previous === PowerState.OFF && this.state !== PowerState.OFF; },
        get cameraStopped() { return this.previous !== PowerState.OFF && this.state === PowerState.OFF; },
        get leftActive() { return this.previous === PowerState.ACTIVE && this.state !== PowerState.ACTIVE; },
      });
      this.state = state;
      this.reason = reason;
      if (state !== PowerState.PAUSED) this.pausedAt = null;
      return transition;
    }
  }

  return {
    WRIST, THUMB, INDEX, MIDDLE, RING, PINKY, FINGERS, PALM, BONES, POSES,
    handPoints, blendPoints, placeHand, makeHand,
    PoseFeatures, features, personHand, roundHalfEven,
    WHEEL_DELTA, State, Action, gestureConfig, intent, GestureMachine,
    EngagementDetector, OneEuroFilter2D,
    rect, clampToScreens,
    DEFAULT_ZONE, toZone, zoneToDesktop, imagePointFor, referencePoint, Pointer,
    preferred, HandLock, DwellClicker,
    PowerState, Reason, PowerMachine,
  };
});
