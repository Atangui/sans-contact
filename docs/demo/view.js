/* Drawing: the iris icon, what SansContact "sees" (points only, never an image) and the side panel.
   Reads state, never changes it. */
(function () {
  "use strict";

  const E = window.SansContactEngine;

  // Studio theme tokens, as in src/sanscontact/ui/icons.py.
  const C = {
    barrel: "#1B1F27", blade: "#262B34", seam: "#6B707A", muted: "#9A9FAB", amber: "#FFB03B", blue: "#8FB3FF",
    candidate: "#D6DAE1", ignored: "#5E6571", grid: "rgba(255,255,255,0.045)", zone: "rgba(255,176,59,0.55)",
  };
  const RIM = { off: C.muted, standby: C.amber, active: C.amber, paused: C.blue };

  // ---- iris icon: same geometry as icons.render_iris (100 x 100 view box) -----------------------
  function rotate([x, y], degrees) {
    const a = (degrees * Math.PI) / 180;
    const px = x - 50;
    const py = y - 50;
    return [50 + px * Math.cos(a) - py * Math.sin(a), 50 + px * Math.sin(a) + py * Math.cos(a)];
  }

  function hexagon(r) {
    const points = [];
    for (let a = 0; a < 360; a += 60) {
      const rad = (a * Math.PI) / 180;
      points.push(`${(50 + r * Math.cos(rad)).toFixed(2)},${(50 + r * Math.sin(rad)).toFixed(2)}`);
    }
    return points;
  }

  function irisSvg(state, small) {
    const rim = RIM[state];
    const stroke = small ? 7 : 5;
    const parts = [
      `<circle cx="50" cy="50" r="49" fill="${rim}"/>`,
      `<circle cx="50" cy="50" r="${49 - stroke}" fill="${C.barrel}"/>`,
      `<circle cx="50" cy="50" r="${41 - (stroke - 5) / 2}" fill="${C.blade}"/>`,
    ];
    if (state === "off") {
      const width = small ? 4 : 2.5;
      for (let k = 0; k < 6; k++) {
        const [x0, y0] = rotate([51.5, 52.6], 60 * k);
        const [x1, y1] = rotate([32.3, 85.87], 60 * k);
        parts.push(`<line x1="${x0.toFixed(2)}" y1="${y0.toFixed(2)}" x2="${x1.toFixed(2)}" y2="${y1.toFixed(2)}" `
          + `stroke="${C.seam}" stroke-width="${width}" stroke-linecap="round"/>`);
      }
      parts.push(`<polygon points="${hexagon(6).join(" ")}" fill="${C.seam}"/>`);
    } else {
      const lens = hexagon(22).join(" ");
      if (state === "standby") {
        parts.push(`<polygon points="${lens}" fill="${rim}" fill-opacity="0.25"/>`);
        parts.push(`<path d="M${hexagon(22).join(" L")} Z M${hexagon(16).join(" L")} Z" fill="${rim}" fill-rule="evenodd"/>`);
      } else if (state === "active") {
        parts.push(`<polygon points="${lens}" fill="${rim}"/>`);
        parts.push(`<circle cx="44" cy="43" r="4" fill="#FFFFFF" fill-opacity="0.55"/>`);
      } else {
        parts.push(`<polygon points="${lens}" fill="${rim}"/>`);
        parts.push(`<rect x="40.8" y="40" width="6.4" height="20" fill="${C.blade}"/>`);
        parts.push(`<rect x="52.8" y="40" width="6.4" height="20" fill="${C.blade}"/>`);
      }
    }
    return `<svg viewBox="0 0 100 100" focusable="false">${parts.join("")}</svg>`;
  }

  function setIris(element, state) {
    if (!element || element.dataset.drawn === state) return;
    element.dataset.drawn = state;
    element.dataset.iris = state;
    element.innerHTML = irisSvg(state, element.classList.contains("small"));
  }

  const decimal = (value, digits = 2) => value.toFixed(digits).replace(".", ",");

  // ---- what SansContact sees: points on a dark canvas ------------------------------------------
  class CameraView {
    constructor(canvas) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.size = [0, 0];
    }

    fit() {
      const box = this.canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      const width = Math.max(1, Math.round(box.width * ratio));
      const height = Math.max(1, Math.round(box.height * ratio));
      if (width !== this.canvas.width || height !== this.canvas.height) {
        this.canvas.width = width;
        this.canvas.height = height;
      }
      this.ratio = ratio;
      this.size = [width, height];
    }

    /** Mirrored preview: the person sees their hand as in a mirror, like the cursor moves. */
    toCanvas(point) {
      return [(1 - point[0]) * this.size[0], point[1] * this.size[1]];
    }

    draw(scene) {
      this.fit();
      const { ctx } = this;
      const [w, h] = this.size;
      const r = this.ratio;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = "#0B0E12";
      ctx.fillRect(0, 0, w, h);
      if (!scene.cameraOn) return;

      ctx.strokeStyle = C.grid;
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let i = 1; i < 8; i++) {
        ctx.moveTo((w * i) / 8, 0);
        ctx.lineTo((w * i) / 8, h);
        ctx.moveTo(0, (h * i) / 8);
        ctx.lineTo(w, (h * i) / 8);
      }
      ctx.stroke();

      const zone = E.DEFAULT_ZONE;
      const [zx0, zy0] = this.toCanvas([zone.x1, zone.y0]);
      const [zx1, zy1] = this.toCanvas([zone.x0, zone.y1]);
      ctx.setLineDash([6 * r, 5 * r]);
      ctx.strokeStyle = scene.power === "active" ? C.zone : "rgba(214,218,225,0.28)";
      ctx.lineWidth = 1.2 * r;
      ctx.strokeRect(zx0, zy0, zx1 - zx0, zy1 - zy0);
      ctx.setLineDash([]);
      ctx.fillStyle = "rgba(214,218,225,0.55)";
      ctx.font = `${11 * r}px Inter, "Segoe UI", system-ui, sans-serif`;
      ctx.textBaseline = "top";
      ctx.fillText("zone active → tout l’écran", zx0, zy1 + 5 * r);

      for (const hand of scene.hands) this.drawHand(hand, scene);

      ctx.fillStyle = "rgba(214,218,225,0.5)";
      ctx.textBaseline = "bottom";
      ctx.fillText("main synthétique · 30 images/s · 640 × 480", 10 * r, h - 8 * r);
    }

    drawHand(hand, scene) {
      const { ctx } = this;
      const r = this.ratio;
      const points = hand.landmarks.map((l) => this.toCanvas(l));
      let color = C.candidate;
      if (hand.role === "ignored") color = C.ignored;
      else if (hand.role === "engaged") color = scene.power === "paused" ? C.blue : C.amber;

      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.strokeStyle = color;
      ctx.lineWidth = 2.6 * r;
      if (hand.role === "ignored") ctx.setLineDash([4 * r, 4 * r]);
      ctx.beginPath();
      for (const [a, b] of E.BONES) {
        ctx.moveTo(points[a][0], points[a][1]);
        ctx.lineTo(points[b][0], points[b][1]);
      }
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = color;
      points.forEach(([x, y], i) => {
        ctx.beginPath();
        ctx.arc(x, y, ([4, 8, 12, 16, 20].includes(i) ? 3.6 : 2.6) * r, 0, Math.PI * 2);
        ctx.fill();
      });

      const pose = hand.pose;
      const center = this.toCanvas(pose.center);
      if (hand.role === "ignored") {
        ctx.font = `${11 * r}px Inter, "Segoe UI", system-ui, sans-serif`;
        ctx.textBaseline = "top";
        ctx.fillStyle = "#AEB3BD";
        ctx.fillText("autre main : ignorée", center[0] - 52 * r, points[0][1] + 10 * r);
        return;
      }

      ctx.strokeStyle = "#FFFFFF";
      ctx.lineWidth = 1.5 * r;
      ctx.beginPath();
      ctx.arc(center[0], center[1], 5 * r, 0, Math.PI * 2);
      ctx.stroke();

      const press = scene.press;
      const release = scene.release;
      for (const [tip, value] of [[8, pose.pinchIndex], [12, pose.pinchMiddle]]) {
        if (value > 0.7 || pose.fist) continue; // in a fist the thumb rests on the fingers: the fist wins
        const [x0, y0] = points[4];
        const [x1, y1] = points[tip];
        ctx.strokeStyle = value < press ? C.amber : value <= release ? "#FFFFFF" : "rgba(255,255,255,0.45)";
        ctx.lineWidth = (value < press ? 2.4 : 1.4) * r;
        ctx.setLineDash(value < press ? [] : [3 * r, 3 * r]);
        ctx.beginPath();
        ctx.moveTo(x0, y0);
        ctx.lineTo(x1, y1);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = ctx.strokeStyle;
        ctx.font = `600 ${11 * r}px "JetBrains Mono", "Cascadia Mono", ui-monospace, monospace`;
        ctx.textBaseline = "middle";
        ctx.fillText(decimal(value), Math.max(x0, x1) + 8 * r, (y0 + y1) / 2);
      }

      if (scene.progress > 0) {
        ctx.strokeStyle = "rgba(255,176,59,0.25)";
        ctx.lineWidth = 4 * r;
        ctx.beginPath();
        ctx.arc(center[0], center[1], 30 * r, 0, Math.PI * 2);
        ctx.stroke();
        ctx.strokeStyle = C.amber;
        ctx.beginPath();
        ctx.arc(center[0], center[1], 30 * r, -Math.PI / 2, -Math.PI / 2 + scene.progress * Math.PI * 2);
        ctx.stroke();
      }
    }
  }

  // ---- side panel ------------------------------------------------------------------------------
  const STATE_LABELS = { off: "Désactivé", standby: "En veille", active: "Actif", paused: "En pause" };

  class Panel {
    constructor(doc) {
      this.stateIris = doc.getElementById("state-iris");
      this.stateLabel = doc.getElementById("state-label");
      this.stateHint = doc.getElementById("state-hint");
      this.machine = [...doc.querySelectorAll("#machine li")];
      this.gauges = { index: doc.getElementById("gauge-index"), middle: doc.getElementById("gauge-middle") };
      this.counts = [...doc.querySelectorAll("[data-count]")];
      this.network = doc.getElementById("net-count");
      this.cameraOff = doc.getElementById("camera-off");
    }

    update(view) {
      setIris(this.stateIris, view.power);
      this.text(this.stateLabel, STATE_LABELS[view.power]);
      this.text(this.stateHint, view.detail);
      this.cameraOff.hidden = view.power !== "off";
      for (const li of this.machine) {
        li.classList.toggle("on", view.power === "active" && li.dataset.state === view.gesture);
      }
      this.gauge(this.gauges.index, view.pinchIndex, view.press, view.release, view.fist);
      this.gauge(this.gauges.middle, view.pinchMiddle, view.press, view.release, view.fist);
      for (const dd of this.counts) this.text(dd, String(view.counts[dd.dataset.count] || 0));
      this.text(this.network, String(view.network));
    }

    gauge(element, value, press, release, fist) {
      const dot = element.querySelector(".gauge-dot");
      const label = element.querySelector(".gauge-value");
      if (value === null) {
        dot.hidden = true;
        this.text(label, "—");
        element.classList.remove("pressed", "band");
        return;
      }
      dot.hidden = false;
      dot.style.left = `${Math.min(value, 1) * 100}%`;
      element.classList.toggle("pressed", !fist && value < press);
      element.classList.toggle("band", !fist && value >= press && value <= release);
      this.text(label, decimal(value));
    }

    text(element, value) {
      if (element.textContent !== value) element.textContent = value;
    }
  }

  window.SansContactView = { irisSvg, setIris, CameraView, Panel, STATE_LABELS, decimal };
})();
