/* The fictitious desktop. It only receives what SansContact sends to Windows with SendInput:
   cursor moves, button presses and releases, wheel steps. Like Windows, it decides by itself what
   a double click or a drag is (4-pixel thresholds, 500 ms double-click time). Everything runs on
   the demo clock, so the guided tour and its captures are reproducible. */
(function () {
  "use strict";

  const DRAG_PX = 4; // SM_CXDRAG
  const DOUBLE_PX = 4; // SM_CXDOUBLECLK
  const DOUBLE_S = 0.5; // GetDoubleClickTime() default
  const WHEEL_PX = 0.4; // 120 units = one notch = 3 lines of 16 px
  const BALLOON_S = 2.8;
  const RIPPLE_S = 0.45;

  const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

  class FakeDesktop {
    constructor(root, now) {
      this.root = root;
      this.now = now;
      this.$ = (selector) => root.querySelector(selector);
      this.cursor = this.$("#cursor");
      this.menu = this.$("#menu");
      this.ghost = this.$("#ghost");
      this.ripple = this.$("#ripple");
      this.balloon = this.$("#balloon");
      this.files = this.$("#files");
      this.windows = [...root.querySelectorAll("[data-win]")];
      this.initial = {
        files: this.files.innerHTML,
        geometry: this.windows.map((w) => [w.style.left, w.style.top]),
      };
      this.timers = [];
      this.reset();
    }

    reset() {
      this.files.innerHTML = this.initial.files;
      this.windows.forEach((w, i) => {
        [w.style.left, w.style.top] = this.initial.geometry[i];
        w.style.zIndex = "";
        w.classList.remove("focused");
      });
      this.$("#win-doc").hidden = true;
      this.$("#win-doc [data-scroll]").scrollTop = 0;
      this.$('[data-task="win-doc"]').hidden = true;
      this.closeMenu();
      this.ghost.hidden = true;
      this.balloon.hidden = true;
      this.ripple.classList.remove("on");
      this.buttons = { left: false, right: false };
      this.pressed = null;
      this.pressedMenu = null;
      this.dragging = null;
      this.menuFile = null;
      this.lastDown = { t: -Infinity, at: [0, 0] };
      this.z = 10;
      this.timers = [];
      this.archived = 0;
      this.focus(this.$("#win-explorer"));
      this.updateCounts();
      const { width, height } = this.size();
      this.position = [Math.round(width * 0.62), Math.round(height * 0.55)];
      this.lastTarget = null;
      this.afterMove();
    }

    size() {
      return { width: Math.round(this.root.clientWidth), height: Math.round(this.root.clientHeight) };
    }

    /** Centre of an element, in desktop pixels. */
    centerOf(target) {
      const element = typeof target === "string" ? this.root.querySelector(target) : target;
      const box = element.getBoundingClientRect();
      const origin = this.root.getBoundingClientRect();
      return [box.left - origin.left + box.width / 2, box.top - origin.top + box.height / 2];
    }

    // ---- what SendInput does -------------------------------------------------------------------
    moveTo(x, y) {
      this.position = [x, y];
      this.lastTarget = [x, y];
      this.afterMove();
    }

    /** The person moves the real mouse: the cursor is no longer where SansContact put it. */
    physicalMove(x, y) {
      this.position = [x, y];
      this.afterMove();
    }

    movedExternally(tolerance) {
      return this.lastTarget !== null && distance(this.position, this.lastTarget) > tolerance;
    }

    forgetPosition() {
      this.lastTarget = null;
    }

    press(button) {
      if (this.buttons[button]) return;
      this.buttons[button] = true;
      this.showRipple(button);
      const hit = this.hit();
      if (button === "right") {
        if (hit.kind === "file") this.select(hit.el);
        return;
      }
      const t = this.now();
      const double = t - this.lastDown.t <= DOUBLE_S && distance(this.position, this.lastDown.at) <= DOUBLE_PX;
      this.lastDown = double ? { t: -Infinity, at: [0, 0] } : { t, at: this.position.slice() };
      if (!this.menu.hidden) {
        if (hit.kind === "menu") {
          this.pressedMenu = hit.el;
          if (hit.el) hit.el.classList.add("pressed");
          return;
        }
        this.closeMenu();
      }
      if (hit.win) this.focus(hit.win);
      if (hit.kind === "file") {
        this.select(hit.el);
        this.pressed = { kind: "file", el: hit.el, start: this.position.slice() };
        if (double) this.open(hit.el);
      } else if (hit.kind === "bar") {
        this.pressed = {
          kind: "window", win: hit.win, start: this.position.slice(), origin: [hit.win.offsetLeft, hit.win.offsetTop],
        };
      } else {
        this.select(null);
        this.pressed = { kind: hit.kind, win: hit.win, start: this.position.slice() };
      }
    }

    release(button) {
      if (!this.buttons[button]) return;
      this.buttons[button] = false;
      const hit = this.hit();
      if (button === "right") {
        if (hit.kind === "file") this.openMenu(hit.el);
        return;
      }
      if (this.pressedMenu !== null || (!this.menu.hidden && hit.kind === "menu")) {
        if (this.pressedMenu && hit.el === this.pressedMenu) this.menuAction(this.pressedMenu.dataset.menu);
        this.pressedMenu = null;
        this.closeMenu();
        return;
      }
      if (this.dragging && this.dragging.kind === "file") this.drop(hit);
      else if (this.pressed && this.pressed.kind === "close" && hit.kind === "close" && hit.win === this.pressed.win) {
        this.closeWindow(hit.win);
      }
      this.dragging = null;
      this.pressed = null;
      this.afterMove();
    }

    /** Wheel units: WHEEL_DELTA (120) is one notch; positive scrolls up (or right when horizontal). */
    wheel(amount, horizontal = false) {
      const hit = this.hit();
      const area = hit.kind === "scroll" ? hit.el : hit.win && hit.win.querySelector("[data-scroll]");
      if (!area) return;
      if (horizontal) area.scrollLeft += amount * WHEEL_PX;
      else area.scrollTop -= amount * WHEEL_PX;
    }

    releaseAll() {
      if (this.buttons.left) this.release("left");
      if (this.buttons.right) this.release("right");
    }

    // ---- timers on the demo clock --------------------------------------------------------------
    tick() {
      const t = this.now();
      this.timers = this.timers.filter(([until, done]) => {
        if (t < until) return true;
        done();
        return false;
      });
      if (this.rippleUntil !== undefined) {
        const k = 1 - Math.max(0, this.rippleUntil - t) / RIPPLE_S;
        this.ripple.style.opacity = String(Math.max(0, 0.9 * (1 - k)));
        this.ripple.style.transform = `translate(${this.rippleAt[0]}px, ${this.rippleAt[1]}px) scale(${0.4 + k * 1.2})`;
        if (k >= 1) this.rippleUntil = undefined;
      }
    }

    later(seconds, done) {
      this.timers.push([this.now() + seconds, done]);
    }

    notify(text) {
      this.balloon.textContent = text;
      this.balloon.hidden = false;
      const token = Symbol("balloon");
      this.balloonToken = token;
      this.later(BALLOON_S, () => { if (this.balloonToken === token) this.balloon.hidden = true; });
    }

    // ---- behaviour -----------------------------------------------------------------------------
    afterMove() {
      const [x, y] = this.position;
      this.cursor.style.transform = `translate(${x}px, ${y}px)`;
      if (this.buttons.left && this.pressed && !this.dragging && distance(this.position, this.pressed.start) > DRAG_PX) {
        if (this.pressed.kind === "file" && !this.pressed.el.classList.contains("folder")) this.startDrag(this.pressed.el);
        else if (this.pressed.kind === "window") this.dragging = { kind: "window" };
      }
      if (this.dragging && this.dragging.kind === "file") {
        this.ghost.style.transform = `translate(${x + 14}px, ${y + 12}px)`;
      } else if (this.dragging && this.dragging.kind === "window") {
        const { win, start, origin } = this.pressed;
        const { width, height } = this.size();
        win.style.left = `${Math.min(Math.max(origin[0] + x - start[0], -win.offsetWidth + 80), width - 80)}px`;
        win.style.top = `${Math.min(Math.max(origin[1] + y - start[1], 0), height - 60)}px`;
      }
      const hit = this.hit();
      for (const element of this.root.querySelectorAll(".hover")) element.classList.remove("hover");
      if (hit.el && (hit.kind === "file" || hit.kind === "icon" || hit.kind === "menu")) hit.el.classList.add("hover");
      if (this.dragging && this.dragging.kind === "file") {
        const target = hit.el && hit.el.closest("[data-drop]");
        if (target && target !== this.dragging.el) target.classList.add("hover");
      }
    }

    hit() {
      const origin = this.root.getBoundingClientRect();
      const px = origin.left + this.position[0];
      const py = origin.top + this.position[1];
      const inside = (el) => {
        if (!el || el.hidden) return false;
        const box = el.getBoundingClientRect();
        return px >= box.left && px < box.right && py >= box.top && py < box.bottom;
      };
      if (!this.menu.hidden && inside(this.menu)) {
        return { kind: "menu", el: [...this.menu.querySelectorAll(".menu-item")].find(inside) || null };
      }
      const windows = this.windows.filter((w) => !w.hidden)
        .sort((a, b) => Number(b.style.zIndex || 0) - Number(a.style.zIndex || 0));
      for (const win of windows) {
        if (!inside(win)) continue;
        const close = win.querySelector("[data-close]");
        if (inside(close)) return { kind: "close", win, el: close };
        if (inside(win.querySelector(".win-bar"))) return { kind: "bar", win };
        const file = [...win.querySelectorAll("[data-file]")].find(inside);
        if (file) return { kind: "file", win, el: file };
        const area = win.querySelector("[data-scroll]");
        if (inside(area)) return { kind: "scroll", win, el: area };
        return { kind: "window", win };
      }
      const icon = [...this.root.querySelectorAll(".dk-icon")].find(inside);
      if (icon) return { kind: "icon", el: icon };
      return { kind: "desktop" };
    }

    focus(win) {
      this.z += 1;
      win.style.zIndex = String(this.z);
      for (const w of this.windows) w.classList.toggle("focused", w === win);
    }

    select(file) {
      for (const element of this.root.querySelectorAll(".selected")) element.classList.remove("selected");
      if (file) file.classList.add("selected");
    }

    open(file) {
      const id = file.dataset.opens;
      if (!id) {
        this.notify(`Ouverture de « ${file.dataset.name} » (fictive).`);
        return;
      }
      const win = this.$(`#${id}`);
      win.hidden = false;
      this.$(`[data-task="${id}"]`).hidden = false;
      this.focus(win);
    }

    closeWindow(win) {
      win.hidden = true;
      const task = this.$(`[data-task="${win.id}"]`);
      if (task) task.hidden = true;
    }

    startDrag(file) {
      this.dragging = { kind: "file", el: file };
      file.classList.add("dragging");
      this.ghost.textContent = file.dataset.name;
      this.ghost.hidden = false;
    }

    drop(hit) {
      const file = this.dragging.el;
      file.classList.remove("dragging");
      this.ghost.hidden = true;
      const target = hit.el && hit.el.closest("[data-drop]");
      if (!target || target === file) return;
      file.remove();
      if (target.dataset.drop === "archives") {
        this.archived += 1;
        this.notify(`« ${file.dataset.name} » déplacé dans Archives.`);
      } else {
        this.notify(`« ${file.dataset.name} » mis à la Corbeille (fictive).`);
      }
      this.updateCounts();
    }

    updateCounts() {
      const count = this.$("#archives-count");
      if (count) count.textContent = `${2 + this.archived} éléments`;
      this.$("#explorer-status").textContent = `${this.files.querySelectorAll("[data-file]").length} éléments`;
    }

    openMenu(file) {
      this.menuFile = file;
      this.$("#menu-title").textContent = file.dataset.name;
      const { width, height } = this.size();
      this.menu.hidden = false;
      const x = Math.min(this.position[0] + 2, width - this.menu.offsetWidth - 4);
      const y = Math.min(this.position[1] + 2, height - this.menu.offsetHeight - 4);
      this.menu.style.left = `${x}px`;
      this.menu.style.top = `${y}px`;
    }

    closeMenu() {
      this.menu.hidden = true;
      for (const element of this.menu.querySelectorAll(".pressed")) element.classList.remove("pressed");
    }

    menuAction(action) {
      const file = this.menuFile;
      if (!file) return;
      if (action === "open") this.open(file);
      else if (action === "delete") {
        file.remove();
        this.updateCounts();
        this.notify(`« ${file.dataset.name} » mis à la Corbeille (fictive).`);
      } else {
        this.notify(`« ${action === "rename" ? "Renommer" : "Copier"} » : action fictive dans cette démo.`);
      }
    }

    showRipple(button) {
      this.rippleAt = this.position.slice();
      this.rippleUntil = this.now() + RIPPLE_S;
      this.ripple.classList.toggle("right", button === "right");
      this.tick();
    }

    /** A short overlay (shortcut chip, physical mouse), hidden after a while on the demo clock. */
    flash(element, seconds) {
      element.hidden = false;
      const token = Symbol("flash");
      element.flashToken = token;
      this.later(seconds, () => { if (element.flashToken === token) element.hidden = true; });
    }
  }

  window.SansContactDesktop = { FakeDesktop };
})();
