# Mesures

Chiffres réels, jamais arrondis à l'avantage. Le banc de mesure complet (cibles de Fitts, tremblement,
faux clics) arrive en phase 4 ; cette page commence avec les mesures de la phase 1.

## Configuration de mesure

| Élément | Valeur |
|---|---|
| Processeur | Intel Core Ultra 7 255H (16 cœurs), 63 Go de mémoire |
| Système | Windows 11 Professionnel 25H2 |
| Caméra | Webcam intégrée « HP 5MP Camera », 640 × 480 demandé |
| Logiciel | Python 3.14.3, OpenCV 5.0.0.93 (opencv-python-headless), modèles ONNX de février 2023 |

## Phase 1 — caméra et détection (23/10/2026)

Mesuré par `scripts/measure_pipeline.py` (aucune image affichée ni enregistrée, souris non pilotée).
**Aucune main n'était devant la caméra** : la recherche de paume tourne donc à chaque image, c'est le cas
le plus lent. Quand une main est suivie, seul le second modèle tourne (≈ 3 ms mesurés hors caméra).

| Mesure | Valeur |
|---|---|
| Modes de lecture comparés | DirectShow seulement : MSMF est absent de ce build d'OpenCV |
| Ouverture de la caméra (DirectShow) | 2,5 à 2,7 s (première image : 3,2 s) |
| Images par seconde, toutes traitées | 29,4 à 29,8 i/s |
| Conversion et passage entre fils | 0,4 ms |

Selon le nombre de fils de calcul d'OpenCV (5 s de mesure chacun) :

| Fils | Détection (moyenne / 95e centile) | Image lue → 21 points (moyenne / 95e centile) | Processeur (tous cœurs) | Mémoire |
|---|---|---|---|---|
| 1 | 21,1 / 22,2 ms | 22,3 / 23,4 ms | 4,5 % | 113 Mo |
| 2 | 14,6 / 16,0 ms | 15,8 / 17,4 ms | 5,8 % | 114 Mo |
| **4 (retenu)** | **9,9 / 10,4 ms** | **10,9 / 11,6 ms** | **7,9 %** | 115 Mo |
| 16 (défaut OpenCV) | 8,0 / 9,6 ms | 9,3 / 11,2 ms | 16,2 % | 115 Mo |

Dans toutes les mesures : 0 tentative de connexion bloquée, 0 connexion vue par le système, caméra libérée
à l'arrêt.

Non mesuré à ce stade : la latence jusqu'au déplacement réel du curseur avec une main (journal technique
de l'application, après le test physique), la latence propre à la caméra avant la lecture de l'image.
