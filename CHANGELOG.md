# Journal des versions

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
