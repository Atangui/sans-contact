# Journal des versions

## [Non publié] — démo en ligne et publication

- Démo interactive sans caméra (`docs/`, GitHub Pages) : une main synthétique pilote un bureau fictif avec une
  traduction JavaScript du moteur, vérifiée image par image contre le Python (`tests/test_demo_engine.py`).
  Visite guidée de tous les gestes et mode « piloter vous-même » (souris et clavier, ou écran tactile).
- La page ne fait aucune requête après chargement (`default-src 'none'`) et affiche son témoin de connexions.
- GIF et captures de la démo (`docs/assets/demo/`), reproductibles par `scripts/capture_demo.js`.
- README complet pour la publication ; liste de contrôle `docs/PUBLICATION.md` ; décisions D40 à D46.

## [Non publié] — phase 2 (gestes)

- Clic gauche (pincer pouce + index), clic droit (pouce + majeur), double clic, glisser-déposer,
  défilement vertical et horizontal à deux doigts, embrayage (poing).
- Machine à états des gestes explicite : hystérésis (appui 0,25 / relâchement 0,38), durées minimales,
  curseur figé et ramené au point visé au début d'un pincement, gel pendant le délai de double clic de Windows.
- Mode relatif avec accélération (option), clic par maintien (option, désactivé).
- Un bouton n'est jamais laissé enfoncé : main perdue, pause, désactivation, sortie.
- Analyse de cohérence des gestes et tests sur séquences synthétiques : `docs/GESTES.md`.

## [Non publié] — phase 1 (socle)

- Machine d'états marche/arrêt (Désactivé, En veille, Actif, En pause), toujours désactivée au lancement.
- Raccourci global `Ctrl + Alt + Maj + Espace`, icône de notification (clic : activer/désactiver ; clic droit : menu),
  témoin « caméra allumée » toujours visible.
- Caméra choisie par son nom (Media Foundation / DirectShow), caméras infrarouges exclues ; dernière image seulement.
- Geste d'engagement (paume ouverte, immobile 1 s), verrouillage sur la main engagée, pointage par le centre de la
  paume, image en miroir, zone active couvrant tout le bureau, filtre One Euro, injection `SendInput` absolue.
- Priorité de la souris physique, détection des fenêtres administrateur (UIPI) et de l'écran sécurisé.
- Libération de la caméra : désactivation, pause de 30 s, verrouillage, veille, écran éteint, changement d'utilisateur, erreur.
- Coupe-réseau au démarrage, témoin des connexions du processus, journal technique sans date.
- Écran d'accord avant la première activation ; « Supprimer toutes mes données ».
- Contrôle de confidentialité avant chaque commit (et sur tout l'historique), intégration continue Windows.
- MediaPipe retiré (télémétrie intégrée) : les modèles de la main (ONNX, OpenCV Zoo, Apache-2.0) tournent
  sur OpenCV avec notre propre traitement (détection de paume, suivi, recadrage, projection).
  Voir `docs/DECISIONS.md` (D4, D5, D24 à D28) et les premières mesures dans `docs/MESURES.md`.
