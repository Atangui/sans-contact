# Licences tierces

Relevées le 23/10/2026 sur PyPI (champ licence du paquet), sauf mention contraire.
Cette liste est mise à jour à chaque changement de dépendance.

## Exécution

| Composant | Version | Rôle | Licence |
|---|---|---|---|
| opencv-python-headless | 5.0.0.93 | Lecture de la caméra, exécution des modèles de la main | Apache-2.0 (inclut FFmpeg, LGPL, jamais utilisé pour le réseau) |
| numpy | 2.5.4 | Calcul numérique | BSD-3-Clause (+ 0BSD, MIT, Zlib, CC0-1.0 pour des parties) |
| pywebview | 6.2.1 | Fenêtre native WebView2 (phase 3) | BSD-3-Clause |
| pythonnet | 3.2.1 | Pont Python ↔ .NET pour WebView2 | MIT |
| clr_loader | 0.3.1 | Dépendance de pythonnet | MIT (fichier LICENSE du dépôt ; PyPI ne l'indique pas) |
| cffi | 2.1.1 | Dépendance de clr_loader | MIT-0 |
| pycparser | 3.12 | Dépendance de cffi | BSD-3-Clause |
| proxy_tools | 0.1.0 | Dépendance de pywebview | MIT |
| bottle | 0.13.4 | Dépendance de pywebview, **jamais démarré** (aucun serveur) | MIT |
| typing_extensions | 4.16.0 | Dépendance de pywebview | PSF-2.0 |

MediaPipe n'est pas utilisé : voir `docs/DECISIONS.md` (D4).

## Développement uniquement (jamais distribué)

| Composant | Version | Rôle | Licence |
|---|---|---|---|
| pip-tools | 7.6.2 | Épinglage des versions avec empreintes | BSD-3-Clause |
| build, pyproject_hooks, setuptools, wheel, pip | 1.6.1, 1.3.3, 84.2.1, 0.48.0, 26.2.2 | Outils de pip-tools | MIT |
| click | 8.5.0 | Dépendance de pip-tools | BSD-3-Clause |
| packaging | 26.3 | Dépendance de build | Apache-2.0 OR BSD-2-Clause |
| pytest | 9.1.1 | Tests | MIT |
| iniconfig, pluggy | 2.3.1, 1.7.0 | Dépendances de pytest | MIT |
| pygments | 2.21.0 | Dépendance de pytest | BSD-2-Clause |
| colorama | 0.4.6 | Dépendance de pytest et click | BSD (classificateur PyPI) |
| ruff | 0.17.2 | Analyse du code | MIT |

La démo en ligne (`docs/`) n'utilise aucun composant tiers. Ses captures sont refaites, au besoin, avec
Node.js, Playwright (Apache-2.0) et ffmpeg (LGPL-2.1 ou plus) : outils facultatifs, non installés par le
projet et jamais distribués.

## Modèles (téléchargés par `scripts/fetch_models.py`, non versionnés)

| Modèle | Source | Licence |
|---|---|---|
| `palm_detection_mediapipe_2023feb.onnx` — SHA-256 `78ff51c38496b7fc8b8ebdb6cc8c1abb02fa6c38427c6848254cdaba57fcce7c` | OpenCV Zoo (`github.com/opencv/opencv_zoo`, commit `48b10fa`), conversion ONNX du modèle MediaPipe de détection de paume | Apache-2.0 (fichier LICENSE du dossier du modèle) |
| `handpose_estimation_mediapipe_2023feb.onnx` — SHA-256 `db0898ae717b76b075d9bf563af315b29562e11f8df5027a1ef07b02bef6d81c` | OpenCV Zoo, même commit, conversion ONNX du modèle MediaPipe des 21 points de la main | Apache-2.0 (fichier LICENSE du dossier du modèle) |

Les paramètres du traitement (ancres, recadrage, projection) reprennent ceux publiés dans le dépôt MediaPipe (Apache-2.0).

## Polices (phase 3)

Archivo, Instrument Sans et IBM Plex Mono : SIL Open Font License 1.1 (vérifié dans le dépôt Google Fonts).
Les fichiers de licence seront joints aux polices embarquées.
