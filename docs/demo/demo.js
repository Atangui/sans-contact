/* Demo wiring: a synthetic hand in front of a fictitious camera, the application's control loop
   (ControlWorker and Controller in src/sanscontact/app.py) and a fictitious desktop.

   Time is simulated: the "camera" delivers 30 frames per second of demo time, whatever the
   display does, so the guided tour always plays out the same way. Nothing is recorded, stored or
   sent: reloading the page starts from scratch. */
(function () {
  "use strict";

  const E = window.SansContactEngine;
  const { CameraView, Panel, setIris } = window.SansContactView;
  const { FakeDesktop } = window.SansContactDesktop;
  const { Tour } = window.SansContactTour;

  const FPS = 30;
  const FRAME_S = 1 / FPS;
  const ASPECT = 4 / 3; // 640 x 480
  const DISENGAGE_AFTER_S = 3.0;
  const PHYSICAL_MOUSE_TOLERANCE_PX = 3;
  const P = E.PowerState;

  // From src/sanscontact/ui/strings.fr.json.
  const HINT = {
    off: "Caméra éteinte, la souris vous appartient.",
    standby: "Caméra allumée. Paume ouverte une seconde pour prendre le contrôle.",
    active: "Votre main pilote le curseur.",
    paused: "Caméra coupée dans {seconds} s sans geste.",
  };
  const REASON = {
    startup: "Au lancement, l’outil est toujours désactivé.",
    hand_lost: "Main sortie du champ.",
    physical_mouse: "Souris physique détectée.",
    pause_timeout: "Caméra libérée après la pause.",
    consent_declined: "Explication non acceptée : la caméra reste éteinte.",
  };

  const clamp01 = (k) => Math.min(Math.max(k, 0), 1);
  const smooth = (k) => k * k * (3 - 2 * k);

  /** Small seeded generator (mulberry32), so the tour's landmark noise is the same every time. */
  function random(seed) {
    let a = seed >>> 0;
    return () => {
      a = (a + 0x6D2B79F5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // ---- the synthetic hand: posture, position, a little tremor and noise ------------------------
  class HandActor {
    constructor({ personHand, size, angleDeg, seed }) {
      Object.assign(this, { personHand, size, angleDeg, seed });
      this.reset();
    }

    reset() {
      this.present = false;
      this.center = [0.5, 1.3];
      this.motion = null;
      this.pose = "relaxed";
      this.from = E.handPoints("relaxed");
      this.to = this.from;
      this.blendStart = 0;
      this.blendDur = 0;
      this.next = random(this.seed);
    }

    enter(at) {
      this.present = true;
      this.center = at.slice();
      this.motion = null;
    }

    leave() {
      this.present = false;
      this.motion = null;
    }

    place(x, y) {
      this.present = true;
      this.center = [x, y];
      this.motion = null;
    }

    setPosture(pose, t, seconds) {
      if (pose === this.pose) return;
      this.from = this.shape(t);
      this.to = E.handPoints(pose, 1.0);
      this.blendStart = t;
      this.blendDur = seconds;
      this.pose = pose;
    }

    shape(t) {
      const k = this.blendDur > 0 ? clamp01((t - this.blendStart) / this.blendDur) : 1;
      return k >= 1 ? this.to : E.blendPoints(this.from, this.to, smooth(k));
    }

    moveTo(target, t, seconds) {
      this.motion = { from: this.position(t).slice(), to: target.slice(), start: t, dur: Math.max(seconds, 1e-6) };
    }

    position(t) {
      const m = this.motion;
      if (!m) return this.center;
      const k = clamp01((t - m.start) / m.dur);
      if (k >= 1) {
        this.center = m.to;
        this.motion = null;
        return this.center;
      }
      const e = smooth(k);
      return [m.from[0] + (m.to[0] - m.from[0]) * e, m.from[1] + (m.to[1] - m.from[1]) * e];
    }

    gauss() {
      const u = Math.max(this.next(), 1e-12);
      return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * this.next());
    }

    /** What the hand model would hand over this frame, or null if the hand is out of the picture. */
    observe(t) {
      if (!this.present) return null;
      const [cx, cy] = this.position(t);
      if (cx < 0.03 || cx > 0.97 || cy < 0.03 || cy > 0.97) return null;
      const phase = this.seed;
      const center = [cx + 0.0009 * Math.sin(4.4 * t + phase), cy + 0.0007 * Math.sin(6.9 * t + 1.3 * phase)];
      const hand = E.placeHand(this.shape(t), {
        center, size: this.size, angleDeg: this.angleDeg, personHand: this.personHand, aspect: ASPECT,
      });
      const sigma = 0.0035 * this.size;
      for (const point of hand.landmarks) {
        point[0] += (this.gauss() * sigma) / ASPECT;
        point[1] += this.gauss() * sigma;
      }
      return hand;
    }
  }

  // ---- the control loop, as in ControlWorker._step and Controller._apply ----------------------
  class Controller {
    constructor(desktop) {
      this.desktop = desktop;
      this.settings = { dwell: false, pointerMode: "absolute" };
      this.reset();
    }

    reset() {
      this.machine = new E.PowerMachine(30.0);
      this.consented = false;
      this.declined = false;
      this.gestures = new E.GestureMachine(E.gestureConfig({ doubleClickS: 0.5 }));
      this.engagement = new E.EngagementDetector(1.0);
      this.lock = new E.HandLock();
      this.dwell = new E.DwellClicker(1.0, 12);
      this.buildPointer();
      this.previous = null;
      this.eventSent = false;
      this.gestureState = E.State.POINT;
      this.observed = [];
      this.focus = null;
    }

    buildPointer() {
      this.pointer = new E.Pointer(E.DEFAULT_ZONE, new E.OneEuroFilter2D(1.0, 0.015, 1.0), this.settings.pointerMode,
        1.0, 0.5, 0.1);
    }

    /** The shortcut or a click on the icon. Returns "consent" when the explanation must be shown first. */
    toggle() {
      if (this.machine.state === P.OFF) {
        if (!this.consented) return "consent";
        this.apply(this.machine.activate());
      } else {
        this.apply(this.machine.deactivate(E.Reason.USER));
      }
      return null;
    }

    acceptConsent() {
      this.consented = true;
      this.declined = false;
      this.apply(this.machine.activate());
    }

    declineConsent() {
      this.declined = true;
    }

    apply(transition) {
      if (!transition) return;
      this.declined = false;
      if (transition.leftActive) {
        this.desktop.releaseAll();
        this.desktop.forgetPosition();
      }
      if (transition.state === P.ACTIVE) this.desktop.forgetPosition();
      if (transition.cameraStopped) this.desktop.releaseAll();
    }

    onState(state) {
      this.eventSent = false;
      this.engagement.reset();
      this.gestures.reset(); // buttons are released by apply() when leaving ACTIVE
      this.dwell.reset();
      if (state === P.ACTIVE) this.pointer.reset(this.desktop.position.slice());
      else this.lock.release();
      this.gestureState = this.gestures.state;
    }

    checkLost(state, t) {
      if (state === P.ACTIVE && !this.eventSent && this.lock.missingFor(t) > DISENGAGE_AFTER_S) {
        this.eventSent = true;
        this.apply(this.machine.handLost());
      }
    }

    /** One camera frame. */
    step(t, hands) {
      this.apply(this.machine.tick(t));
      let state = this.machine.state;
      if (state !== this.previous) {
        this.onState(state);
        this.previous = state;
      }
      this.focus = null;
      this.observed = [];
      if (state === P.OFF) return; // camera released: no frame at all
      const candidates = hands.map((hand) => [hand, E.features(hand, ASPECT)]);
      this.observed = candidates;
      if (state === P.STANDBY || state === P.PAUSED) {
        const candidate = E.preferred(candidates, "any");
        this.focus = candidate;
        if (this.engagement.update(candidate ? candidate[1] : null, t, ASPECT) && candidate) {
          this.lock.engage(candidate, t);
          this.apply(this.machine.engaged());
        }
        return;
      }
      if (state !== P.ACTIVE || this.eventSent) return;
      const selected = this.lock.select(candidates, t, ASPECT);
      if (selected === null) {
        const frame = this.gestures.handMissing(t);
        this.gestureState = frame.state;
        this.execute(frame.actions);
        this.checkLost(state, t);
        return;
      }
      this.focus = selected;
      const [hand, pose] = selected;
      const frame = this.gestures.update(pose, t, ASPECT);
      this.gestureState = frame.state;
      const [x, y] = E.referencePoint(hand, pose, "palm_center");
      const { width, height } = this.desktop.size();
      const screen = E.rect(0, 0, width, height);
      const [px, py] = this.pointer.update(x, y, t, screen, [screen], frame.freeze, frame.rollback);
      let actions = frame.actions;
      const dwellAllowed = this.settings.dwell && frame.state === E.State.POINT && !frame.freeze;
      if (this.dwell.update([px, py], t, dwellAllowed)) {
        actions = actions.concat([{ action: E.Action.LEFT_DOWN }, { action: E.Action.LEFT_UP }]);
      }
      state = this.machine.state;
      if (state !== P.ACTIVE) return;
      if (this.desktop.movedExternally(PHYSICAL_MOUSE_TOLERANCE_PX)) {
        this.eventSent = true;
        this.apply(this.machine.pointerTaken(E.Reason.PHYSICAL_MOUSE, t));
        return;
      }
      const last = this.desktop.lastTarget;
      if (!last || last[0] !== px || last[1] !== py) this.desktop.moveTo(px, py);
      this.execute(actions);
    }

    execute(actions) {
      for (const item of actions) {
        if (item.action === E.Action.LEFT_DOWN) this.desktop.press("left");
        else if (item.action === E.Action.LEFT_UP) this.desktop.release("left");
        else if (item.action === E.Action.RIGHT_DOWN) this.desktop.press("right");
        else if (item.action === E.Action.RIGHT_UP) this.desktop.release("right");
        else if (item.action === E.Action.WHEEL) this.desktop.wheel(item.amount);
        else if (item.action === E.Action.HWHEEL) this.desktop.wheel(item.amount, true);
      }
    }

    roleOf(hand) {
      if (this.focus && hand === this.focus[0]) return this.machine.state === P.STANDBY ? "candidate" : "engaged";
      return "ignored";
    }

    detail(t) {
      const state = this.machine.state;
      if (state === P.OFF && this.declined) return REASON.consent_declined;
      const reason = REASON[this.machine.reason] || "";
      if (state === P.PAUSED) {
        const seconds = Math.max(0, Math.ceil(this.machine.pauseRemaining(t)));
        return `${reason} ${HINT.paused.replace("{seconds}", seconds)}`.trim();
      }
      return reason || HINT[state];
    }
  }

  // ---- the page --------------------------------------------------------------------------------
  const LIVE_HELP = {
    off: "Activez SansContact : bouton « Activer », icône de la barre des tâches ou Ctrl + Alt + Maj + Espace.",
    standby: "Votre souris sur la vue caméra joue la main. Maintenez O (paume ouverte), immobile, une seconde.",
    active: "Déplacez la main. Clic gauche maintenu : pincer pouce + index · clic droit : pouce + majeur · "
      + "D : deux doigts (défiler) · F : poing.",
    paused: "En pause : paume ouverte (O) une seconde pour reprendre.",
  };
  const TOUCH_HELP = {
    off: "Touchez « Activer » pour allumer la caméra (fictive).",
    standby: "Posez un doigt sur la vue caméra : c’est la main. Touchez « Paume ouverte » et restez immobile.",
    active: "Glissez le doigt sur la vue caméra. Les boutons choisissent la posture (pincer, deux doigts, poing).",
    paused: "En pause : « Paume ouverte » une seconde pour reprendre.",
  };
  const POSTURE_KEYS = { o: "open", " ": "pinch_index", m: "pinch_middle", d: "two_fingers", f: "fist" };
  const PRIORITY = ["pinch_middle", "pinch_index", "fist", "two_fingers", "open"];

  class Demo {
    constructor() {
      this.t = 0;
      const $ = (id) => document.getElementById(id);
      this.$ = $;
      this.desktop = new FakeDesktop($("desktop"), () => this.t);
      this.controller = new Controller(this.desktop);
      this.hand = new HandActor({ personHand: "right", size: 0.2, angleDeg: -8, seed: 7 });
      this.other = new HandActor({ personHand: "left", size: 0.17, angleDeg: 14, seed: 11 });
      this.camera = new CameraView($("camera"));
      this.panel = new Panel(document);
      this.tour = new Tour();
      this.params = new URLSearchParams(window.location.search);
      this.capture = this.params.has("capture");
      this.coarse = window.matchMedia("(pointer: coarse)").matches;
      this.keys = new Set(); // postures held on the keyboard
      this.buttons = new Set(); // pinches held with the mouse buttons over the camera view
      this.latched = new Set(); // postures locked with the on-screen buttons
      this.mouseMotion = null;
      this.director = this.makeDirector();
      this.bind();
      for (const element of document.querySelectorAll("[data-iris]")) setIris(element, element.dataset.iris);
      if (this.params.get("mode") === "live") this.startLive();
      else this.startTour();
      if (!this.capture && window.matchMedia("(prefers-reduced-motion: reduce)").matches && this.mode === "tour") {
        this.playing = false; // the tour waits for the visitor instead of animating on its own
        $("btn-pause").textContent = "Lancer";
      }
      this.render();
      if (!this.capture) {
        this.lastNow = null;
        this.accumulator = 0;
        window.requestAnimationFrame((now) => this.loop(now));
      }
    }

    // ---- modes -----------------------------------------------------------------------------
    resetAll() {
      this.desktop.reset();
      this.controller.reset();
      this.hand.reset();
      this.other.reset();
      this.mouseMotion = null;
      this.keys.clear();
      this.buttons.clear();
      this.latched.clear();
      this.$("consent").hidden = true;
      this.$("consent-yes").classList.remove("pressed");
      this.$("phys-mouse").hidden = true;
      this.$("keychip").hidden = true;
      for (const button of document.querySelectorAll("[data-posture]")) button.setAttribute("aria-pressed", "false");
    }

    startTour() {
      this.mode = "tour";
      this.playing = true;
      this.stepNumber = 0;
      this.resetAll();
      this.tour.restart(this.t);
      this.tour.advance(this.director); // first caption right away, even before the clock runs
      document.body.classList.add("touring");
      document.body.classList.remove("living");
      this.$("live").hidden = true;
      this.$("btn-pause").hidden = false;
      this.$("btn-pause").textContent = "Pause";
      this.$("btn-tour").classList.add("primary");
      this.$("btn-live").classList.remove("primary");
      this.$("camera-activate").hidden = true;
    }

    startLive() {
      this.mode = "live";
      this.playing = true;
      this.resetAll();
      document.body.classList.remove("touring");
      document.body.classList.add("living");
      this.$("live").hidden = false;
      this.$("btn-pause").hidden = true;
      this.$("btn-tour").classList.remove("primary");
      this.$("btn-live").classList.add("primary");
      this.$("camera-activate").hidden = false;
      this.$("step").textContent = "À vous";
    }

    makeDirector() {
      const demo = this;
      return {
        get t() { return demo.t; },
        hand: demo.hand,
        other: demo.other,
        say(text) {
          demo.stepNumber += 1;
          demo.$("step").textContent = `${demo.stepNumber}/${demo.tour.total}`;
          demo.$("caption").textContent = text;
        },
        aim(target) {
          const [px, py] = typeof target === "string" ? demo.desktop.centerOf(target) : target;
          const { width, height } = demo.desktop.size();
          return E.imagePointFor(px, py, E.rect(0, 0, width, height));
        },
        key(text) {
          const chip = demo.$("keychip");
          chip.textContent = text;
          demo.desktop.flash(chip, 1.6);
        },
        hotkey() { demo.toggle(); },
        pressConsent() { demo.$("consent-yes").classList.add("pressed"); },
        acceptConsent() { demo.acceptConsent(); },
        physicalMouse(delta, seconds) {
          const from = demo.desktop.position.slice();
          demo.mouseMotion = { from, to: [from[0] + delta[0], from[1] + delta[1]], start: demo.t, dur: seconds };
          demo.desktop.flash(demo.$("phys-mouse"), seconds + 1.4);
        },
      };
    }

    toggle() {
      if (this.controller.toggle() === "consent") this.$("consent").hidden = false;
    }

    acceptConsent() {
      this.$("consent").hidden = true;
      this.$("consent-yes").classList.remove("pressed");
      this.controller.acceptConsent();
    }

    // ---- time --------------------------------------------------------------------------------
    frame() {
      this.t += FRAME_S;
      if (this.mode === "tour") {
        this.tour.advance(this.director);
        if (this.tour.done) this.startTour();
      } else {
        this.updateLivePosture();
      }
      if (this.mouseMotion) {
        const m = this.mouseMotion;
        const k = smooth(clamp01((this.t - m.start) / m.dur));
        this.desktop.physicalMove(m.from[0] + (m.to[0] - m.from[0]) * k, m.from[1] + (m.to[1] - m.from[1]) * k);
        if (k >= 1) this.mouseMotion = null;
      }
      const hands = this.controller.machine.cameraOn
        ? [this.hand, this.other].map((h) => h.observe(this.t)).filter(Boolean)
        : [];
      this.controller.step(this.t, hands);
      this.desktop.tick();
    }

    /** For the capture script: advance the demo clock by whole camera frames, then draw. */
    advance(frames) {
      for (let i = 0; i < frames; i++) this.frame();
      this.render();
    }

    loop(now) {
      if (this.lastNow !== null && this.playing) {
        this.accumulator = Math.min(this.accumulator + (now - this.lastNow) / 1000, 0.25);
        while (this.accumulator >= FRAME_S) {
          this.accumulator -= FRAME_S;
          this.frame();
        }
      }
      this.lastNow = now;
      this.render();
      window.requestAnimationFrame((next) => this.loop(next));
    }

    // ---- drawing -----------------------------------------------------------------------------
    render() {
      const c = this.controller;
      const power = c.machine.state;
      const config = c.gestures.config;
      const standby = power === P.STANDBY || power === P.PAUSED;
      this.camera.draw({
        cameraOn: c.machine.cameraOn,
        power,
        hands: c.observed.map(([hand, pose]) => ({ landmarks: hand.landmarks, pose, role: c.roleOf(hand) })),
        progress: standby ? c.engagement.progress(this.t) : 0,
        press: config.press,
        release: config.release,
      });
      const pose = c.focus ? c.focus[1] : null;
      this.panel.update({
        power,
        detail: c.detail(this.t),
        gesture: c.gestureState,
        pinchIndex: pose ? pose.pinchIndex : null,
        pinchMiddle: pose ? pose.pinchMiddle : null,
        fist: pose ? pose.fist : false,
        press: config.press,
        release: config.release,
        counts: c.gestures.counts,
        network: window.SansContactNetwork ? window.SansContactNetwork.count() : 0,
      });
      setIris(this.$("tray-iris"), power);
      setIris(this.$("indicator-iris"), power === P.OFF ? "standby" : power);
      this.$("indicator").hidden = power === P.OFF;
      const cursor = this.$("cursor");
      cursor.dataset.gesture = power === P.ACTIVE ? c.gestureState : power;
      const phys = this.$("phys-mouse");
      if (!phys.hidden) {
        const [x, y] = this.desktop.position;
        phys.style.transform = `translate(${x + 22}px, ${y + 18}px)`;
      }
      if (this.mode === "live") {
        this.$("caption").textContent = (this.coarse ? TOUCH_HELP : LIVE_HELP)[power];
        this.$("btn-power").textContent = power === P.OFF ? "Activer" : "Désactiver";
        this.$("camera-activate").hidden = power !== P.OFF;
      }
    }

    // ---- live mode input -----------------------------------------------------------------------
    updateLivePosture() {
      const wanted = PRIORITY.find((pose) => this.keys.has(pose) || this.buttons.has(pose) || this.latched.has(pose))
        || "relaxed";
      const pinch = wanted.startsWith("pinch") || this.hand.pose.startsWith("pinch");
      this.hand.setPosture(wanted, this.t, pinch ? 0.12 : 0.15);
    }

    placeFromPointer(event) {
      const box = this.$("camera").getBoundingClientRect();
      const x = (event.clientX - box.left) / box.width;
      const y = (event.clientY - box.top) / box.height;
      this.hand.place(1 - x, y); // the preview is mirrored
    }

    bind() {
      const $ = this.$;
      $("btn-tour").addEventListener("click", () => this.startTour());
      $("btn-live").addEventListener("click", () => this.startLive());
      $("btn-pause").addEventListener("click", () => {
        this.playing = !this.playing;
        $("btn-pause").textContent = this.playing ? "Pause" : "Reprendre";
      });
      const toggle = () => { if (this.mode === "live") this.toggle(); };
      $("btn-power").addEventListener("click", toggle);
      $("tray").addEventListener("click", toggle);
      $("camera-activate").addEventListener("click", toggle);
      $("consent-yes").addEventListener("click", () => { if (this.mode === "live") this.acceptConsent(); });
      $("consent-no").addEventListener("click", () => {
        if (this.mode !== "live") return;
        $("consent").hidden = true;
        this.controller.declineConsent();
      });
      $("opt-dwell").addEventListener("change", (e) => { this.controller.settings.dwell = e.target.checked; });
      $("opt-relative").addEventListener("change", (e) => {
        this.controller.settings.pointerMode = e.target.checked ? "relative" : "absolute";
        this.controller.buildPointer();
        this.controller.pointer.reset(this.desktop.position.slice());
      });

      const canvas = $("camera");
      canvas.addEventListener("contextmenu", (e) => e.preventDefault());
      canvas.addEventListener("pointerenter", (e) => {
        if (this.mode === "live" && e.pointerType === "mouse") this.placeFromPointer(e);
      });
      canvas.addEventListener("pointermove", (e) => {
        if (this.mode !== "live") return;
        if (e.pointerType === "mouse" || e.buttons) this.placeFromPointer(e);
      });
      canvas.addEventListener("pointerdown", (e) => {
        if (this.mode !== "live") return;
        this.placeFromPointer(e);
        if (e.pointerType !== "mouse") {
          canvas.setPointerCapture(e.pointerId);
          return;
        }
        if (e.button === 0) this.buttons.add("pinch_index");
        if (e.button === 2) this.buttons.add("pinch_middle");
      });
      const up = (e) => {
        if (e.pointerType !== "mouse") {
          this.hand.leave();
          return;
        }
        if (e.button === 0) this.buttons.delete("pinch_index");
        if (e.button === 2) this.buttons.delete("pinch_middle");
      };
      canvas.addEventListener("pointerup", up);
      canvas.addEventListener("pointercancel", up);
      canvas.addEventListener("pointerleave", (e) => {
        if (e.pointerType !== "mouse") return;
        this.buttons.clear();
        this.hand.leave();
      });

      for (const button of document.querySelectorAll("[data-posture]")) {
        button.setAttribute("aria-pressed", "false");
        button.addEventListener("click", () => {
          const pose = button.dataset.posture;
          if (this.latched.has(pose)) this.latched.delete(pose);
          else this.latched.add(pose);
          button.setAttribute("aria-pressed", String(this.latched.has(pose)));
        });
      }

      document.addEventListener("keydown", (e) => {
        if (this.mode !== "live" || e.repeat) return;
        if (e.ctrlKey && e.altKey && e.shiftKey && e.code === "Space") {
          e.preventDefault();
          this.toggle();
          return;
        }
        if (e.ctrlKey || e.altKey || e.metaKey) return;
        const pose = POSTURE_KEYS[e.code === "Space" ? " " : e.key.toLowerCase()];
        if (!pose) return;
        if (e.code === "Space") e.preventDefault();
        this.keys.add(pose);
      });
      document.addEventListener("keyup", (e) => {
        const pose = POSTURE_KEYS[e.code === "Space" ? " " : e.key.toLowerCase()];
        if (pose) this.keys.delete(pose);
      });
      window.addEventListener("blur", () => {
        this.keys.clear();
        this.buttons.clear();
      });
    }
  }

  const demo = new Demo();
  window.SansContactDemo = {
    advance: (frames) => demo.advance(frames),
    get t() { return demo.t; },
    get tourDone() { return demo.tour.done; },
    get step() { return demo.stepNumber; },
    get counts() { return { ...demo.controller.gestures.counts }; },
    get power() { return demo.controller.machine.state; },
  };
})();
