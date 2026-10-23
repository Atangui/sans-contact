# SansContact

> **Le geste suffit.** Piloter Windows avec la main, devant une simple webcam. Tout reste sur le PC.

**English summary.** SansContact is a Windows prototype that moves the mouse pointer with hand gestures in front
of a regular webcam, with privacy by design: 100 % local, no network, no stored image, camera released as soon
as it is not needed. Work in progress (phase 1 of 7).

## État

Phase 1 (socle) en cours. Le README complet, les captures et la démo arriveront en phase 7.

## Lancer (développement)

Prérequis : Windows 10 ou 11, Python 3.14, sans droits administrateur.

```bat
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install --require-hashes --no-deps -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python.exe scripts\fetch_models.py
.venv\Scripts\python.exe scripts\install_hooks.py
SansContact.cmd
```

Tests : `.venv\Scripts\python.exe -m pytest` (aucune caméra nécessaire, points synthétiques uniquement).

## Vie privée

Voir [docs/CONFIDENTIALITE.md](docs/CONFIDENTIALITE.md).

## Crédits

Conçu et développé par Charles Atangui. Licence [MIT](LICENSE).
