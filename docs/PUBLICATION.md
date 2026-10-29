# Publication — liste de contrôle

Rien n’est publié sans cette liste (voir `CLAUDE.md`). Publication du dépôt et de la démo GitHub Pages
demandée par l’utilisateur le 29/10/2026, avant la phase 7, pour son portfolio.

## Vérifié avant l’envoi (29/10/2026)

- [x] Contrôle de confidentialité sur tous les fichiers suivis (`scripts/privacy_check.py --all-files`) : OK.
- [x] Contrôle sur tout l’historique, messages et auteurs compris (`--history`) : OK. Les quatre commits des
      phases 1 et 2 sont publiés tels quels ; toutes les adresses d’auteur sont des adresses « noreply ».
- [x] Aucune image ni vidéo hors de `docs/assets/demo/`. Les quatre fichiers de ce dossier (`demo.gif`,
      `accord.png`, `prise-de-controle.png`, `glisser-deposer.png`) sont des captures de la démo : main
      synthétique, bureau et fichiers fictifs, aucune caméra. Chacun a été regardé avant l’envoi.
- [x] Aucun chemin local, lien privé ou adresse e-mail personnelle dans les fichiers ni dans l’historique.
- [x] Fichiers privés absents du dépôt et ignorés par git : brief initial, `.privacy-patterns.local`,
      `config.local.json`, `settings.json`.
- [x] Modèles ONNX non versionnés (`models/` ignoré) : téléchargés et vérifiés par `scripts/fetch_models.py`.
- [x] Démo : aucune requête après le chargement (politique `default-src 'none'`, scripts et styles du même
      site, polices du système). Témoin de connexions à 0 sur la visite guidée complète et en mode libre,
      vérifié dans Chromium ; aucune erreur dans la console.
- [x] Démo : le moteur JavaScript donne les mêmes résultats que le Python (`tests/test_demo_engine.py`).
- [x] Démo : affichage vérifié en 1280 × 720 et sur une largeur de téléphone (390 px, sans défilement
      horizontal).
- [x] Licence MIT, `THIRD_PARTY_LICENSES.md` et `SECURITY.md` présents.

## À faire par vous

Ces points ne peuvent pas être faits depuis la session qui a préparé la publication.

- [ ] Relancer le contrôle **avec vos motifs locaux** : `scripts\privacy_check.py --all-files` puis
      `--history`. La vérification ci-dessus a tourné sans `.privacy-patterns.local`, qui n’existe que sur
      votre PC (c’est voulu).
- [ ] Activer GitHub Pages : Settings › Pages › *Deploy from a branch*, la branche publiée, dossier `/docs`.
      La démo sera alors à l’adresse indiquée dans le README.
- [ ] Activer le signalement privé des failles (Settings › Code security › *Private vulnerability
      reporting*) : `SECURITY.md` demande de passer par lui.
- [ ] Vérifier que l’intégration continue (Windows) passe sur GitHub Actions.
- [ ] Facultatif : description du dépôt et lien vers la démo dans « About ».
