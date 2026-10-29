/* The guided tour: a script for the synthetic hand. It only moves the hand, changes its posture
   and presses the shortcut; every click, drag or scroll on the desktop comes from the engine.
   Each step returns how long to wait before the next one (in seconds of demo time). */
(function () {
  "use strict";

  const say = (text) => Object.assign((a) => { a.say(text); return 0; }, { caption: text });
  const wait = (seconds) => () => seconds;
  const move = (target, seconds, blocking = true) => (a) => {
    a.hand.moveTo(a.aim(target), a.t, seconds);
    return blocking ? seconds : 0;
  };
  const shift = (dx, dy, seconds) => (a) => {
    const [x, y] = a.hand.position(a.t);
    a.hand.moveTo([x + dx, y + dy], a.t, seconds);
    return seconds;
  };
  const posture = (pose, seconds = 0.2, blocking = true) => (a) => {
    a.hand.setPosture(pose, a.t, seconds);
    return blocking ? seconds : 0;
  };
  const pinch = (pose, close = 0.16, hold = 0.14, open = 0.16) => [posture(pose, close), wait(hold),
    posture("relaxed", open)];

  const STEPS = [
    say("Au lancement, SansContact est toujours désactivé : caméra éteinte, la souris vous appartient."),
    wait(2.6),

    say("Raccourci Ctrl + Alt + Maj + Espace. Avant la première activation, l’outil explique ce qu’il filme."),
    (a) => { a.key("Ctrl + Alt + Maj + Espace"); a.hotkey(); return 3.4; },
    (a) => { a.pressConsent(); return 0.35; },
    (a) => { a.acceptConsent(); return 0.5; },

    say("Caméra allumée, en veille. SansContact ne garde que 21 points par main, jamais l’image."),
    (a) => { a.hand.enter([0.66, 1.05], a.t); a.hand.moveTo([0.5, 0.5], a.t, 1.2); return 2.4; },

    say("Paume ouverte, immobile une seconde : la main prend le contrôle."),
    posture("open", 0.25),
    wait(1.6),

    say("Le centre de la paume pilote le curseur : image en miroir, mouvement lissé (filtre One Euro)."),
    posture("relaxed", 0.25, false),
    move('[data-name="Affiche-salon.pdf"]', 1.3),
    wait(0.5),

    say("Pincer pouce + index : clic. Le curseur se fige pour que le clic tombe là où l’on vise."),
    ...pinch("pinch_index"),
    wait(0.7),

    say("Deux pincements rapides : double clic, dans le délai de Windows."),
    move('[data-name="Note-de-cadrage.txt"]', 1.0),
    wait(0.45),
    ...pinch("pinch_index", 0.1, 0.08, 0.1),
    ...pinch("pinch_index", 0.1, 0.08, 0.1),
    wait(0.9),

    say("Index et majeur tendus : défilement. Plus la main s’éloigne, plus ça défile vite."),
    move("#win-doc .doc", 1.0),
    wait(0.3),
    posture("two_fingers", 0.2),
    wait(0.4),
    shift(0, 0.07, 0.5),
    wait(1.5),
    shift(0, -0.07, 0.4),
    posture("relaxed", 0.2),
    wait(0.4),

    say("Pincer, déplacer, relâcher : glisser-déposer."),
    move('[data-name="Budget-2027.xlsx"]', 1.0),
    wait(0.4),
    posture("pinch_index", 0.16),
    wait(0.25),
    move('[data-name="Archives"]', 1.2),
    wait(0.3),
    posture("relaxed", 0.16),
    wait(0.9),

    say("Pouce + majeur : clic droit, le menu contextuel s’ouvre."),
    move('[data-name="Plan-du-stand.svg"]', 1.0),
    wait(0.4),
    ...pinch("pinch_middle", 0.18, 0.15, 0.18),
    wait(1.3),
    move("#explorer-status", 0.7),
    wait(0.35),
    ...pinch("pinch_index"),
    wait(0.5),

    say("Poing fermé : embrayage. Le curseur reste figé, rien n’est cliqué."),
    posture("fist", 0.15),
    wait(0.3),
    shift(-0.07, 0.04, 0.6),
    shift(0.07, -0.04, 0.6),
    posture("relaxed", 0.15),
    wait(0.6),

    say("Une autre main dans le champ ? Elle est ignorée : seule la main engagée pilote."),
    (a) => { a.other.enter([0.86, 1.05], a.t); a.other.moveTo([0.82, 0.5], a.t, 0.8); return 1.0; },
    (a) => { a.other.setPosture("pinch_index", a.t, 0.15); return 0.4; },
    (a) => { a.other.setPosture("relaxed", a.t, 0.15); return 0.4; },
    (a) => { a.other.setPosture("pinch_middle", a.t, 0.15); return 0.4; },
    (a) => { a.other.setPosture("relaxed", a.t, 0.15); return 0.3; },
    (a) => { a.other.moveTo([0.86, 1.08], a.t, 0.6); return 0.6; },
    (a) => { a.other.leave(); return 0.2; },

    say("La souris physique est prioritaire : SansContact se met aussitôt en pause."),
    (a) => { a.physicalMouse([70, 44], 0.6); return 2.2; },

    say("Paume ouverte, immobile une seconde : on reprend."),
    posture("open", 0.25),
    wait(1.5),
    posture("relaxed", 0.25),
    wait(0.3),

    say("Main sortie du champ : boutons relâchés, puis veille au bout de 3 secondes."),
    (a) => { const [x] = a.hand.position(a.t); a.hand.moveTo([x, 1.3], a.t, 0.7); return 0.7; },
    (a) => { a.hand.leave(); return 3.5; },

    say("Ctrl + Alt + Maj + Espace : tout s’arrête, la caméra est libérée."),
    (a) => { a.key("Ctrl + Alt + Maj + Espace"); a.hotkey(); return 2.6; },

    say("Fin de la visite. « Piloter vous-même » : votre souris devient la main synthétique."),
    wait(3.2),
  ];

  class Tour {
    constructor(steps = STEPS) {
      this.steps = steps;
      this.total = steps.filter((step) => step.caption).length;
      this.restart(0);
    }

    restart(t) {
      this.index = 0;
      this.nextAt = t;
      this.done = false;
    }

    /** Runs every step that is due. Times add up from the schedule, never from the real clock. */
    advance(director) {
      while (!this.done && director.t >= this.nextAt - 1e-9) {
        const step = this.steps[this.index];
        this.index += 1;
        if (!step) {
          this.done = true;
          break;
        }
        this.nextAt += step(director) || 0;
      }
    }
  }

  window.SansContactTour = { Tour, STEPS };
})();
