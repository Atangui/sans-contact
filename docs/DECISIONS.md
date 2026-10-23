# Décisions prises en cours de route

Chaque décision qui ne figurait pas dans le cahier des charges est notée ici et signalée.

## Phase 0 — diagnostic

| # | Décision | Pourquoi |
|---|---|---|
| D1 | Python 3.14 (3.14.3, déjà installé) | Plus récente version déclarée compatible par MediaPipe (3.9 à 3.14). Python 3.15 n'est pas déclaré. Mise à jour corrective vers 3.14.9 laissée à plus tard. |
| D2 | Icône de notification écrite en Win32 direct (`Shell_NotifyIcon`), sans `pystray` | Pas de dépendance LGPL ; une seule boucle de messages Windows (raccourci, session, veille, icône, témoin) ; pas de conflit avec la boucle de pywebview. |
| D3 | Mesures CPU et mémoire par l'API Windows, sans `psutil` | Une dépendance de moins. |

## Phase 1 — socle

| # | Décision | Pourquoi |
|---|---|---|
| D4 | **Écart avec le cahier des charges, décidé par l'utilisateur :** MediaPipe n'est plus utilisé. Sa bibliothèque native (`libmediapipe.dll`, version 1.1.1 de PyPI) embarque le client de télémétrie interne de Google « Clearcut » (`play.googleapis.com/log`, envoi via WinINet, journal d'événements sur disque). Constat vérifié dans les deux sessions ; aucune détection MediaPipe n'a jamais été lancée. MediaPipe et ses dépendances inutiles (sounddevice, matplotlib, certifi…) ont été désinstallés ; `opencv-contrib-python` est remplacé par `opencv-python-headless` (sans module de reconnaissance faciale). Un test échoue si ces paquets reviennent. | Règle 3.1 (aucune connexion réseau) : les règles l'emportent sur la pile prévue (« MediaPipe, API Tasks »). Le coupe-réseau Python ne voit pas le code natif. |
| D5 | Les modèles de la main sont exécutés par OpenCV (`perception/opencv_hands.py`), avec notre propre pré- et post-traitement (ancres, décodage, fusion des détections, recadrage tourné, projection, suivi d'une image à l'autre), repris des paramètres publiés par MediaPipe (`perception/hand_geometry.py`). La paume n'est recherchée que lorsqu'aucune main n'est suivie. | Choix de l'utilisateur (option A). |
| D24 | Format des modèles, avec l'accord de l'utilisateur : versions ONNX des modèles MediaPipe de février 2023 publiées par OpenCV Zoo (licence Apache-2.0 écrite dans le dépôt), épinglées sur un commit, empreintes SHA-256 identiques à celles publiées. OpenCV en lit toutes les sorties en un passage (≈ 3 ms par modèle). Le format officiel `.tflite` n'était pas utilisable : OpenCV 5.0 n'expose pas sa sortie « points à l'écran ». | Seule voie « OpenCV » qui fonctionne ; règle aussi la licence incertaine du modèle de Google. |
| D25 | Les modes tête et regard (phases 5 et 6) demanderont le même travail pour les modèles du visage (détection du visage, points du visage et de l'iris) : exécution hors MediaPipe, pré- et post-traitement écrits par nous. | Conséquence de D4. |
| D6 | Modèles épinglés (adresse fixe), empreinte SHA-256 vérifiée au téléchargement **et** avant chaque allumage de la caméra, puis chargés depuis la mémoire. | Ce qui tourne est exactement ce qui a été vérifié. |
| D26 | Lecture caméra par DirectShow. Dans OpenCV 5.0.0.93 (PyPI), le mode MSMF est listé mais absent (`hasBackend(MSMF) = False`) : la comparaison demandée a donc un seul candidat mesurable (ouverture ≈ 2,5 s, 29,8 i/s en 640 × 480). | Mesuré, voir `docs/MESURES.md`. |
| D27 | Calcul OpenCV limité à 4 fils. Mesuré sans main visible (recherche de paume à chaque image) : 10 ms et 7,9 % du processeur, contre 8 ms et 16 % avec tous les fils. Réglable (`opencv_threads`). | Laisser le processeur aux autres applications. |
| D28 | OpenCV contient FFmpeg, capable d'ouvrir des flux réseau. SansContact n'ouvre jamais qu'un numéro de caméra (DirectShow), jamais une adresse. Le coupe-réseau et le témoin réseau restent actifs. | Documenté honnêtement (3.1). |
| D7 | Raccourci par défaut `Ctrl + Alt + Maj + Espace` au lieu de `Ctrl + Alt + Espace` (maquette). | `Ctrl + Alt + Espace` est déjà pris par une autre application sur le PC de test (erreur Windows 1409). La nouvelle combinaison est libre et n'est pas utilisée par Office. Modifiable dans les réglages. |
| D8 | Après 30 s de pause, l'outil passe à **Désactivé** (iris fermé), et non « En pause, caméra éteinte ». | Un iris ouvert avec une caméra éteinte mentirait : la métaphore doit dire la vérité. |
| D9 | Écran éteint (veille moderne) traité comme une mise en veille : caméra libérée. | Sur les portables récents, la veille moderne n'envoie pas toujours l'événement de mise en veille classique. Option `release_on_display_off`. |
| D10 | Journal technique sans date ni heure (temps depuis le démarrage seulement), 512 Ko maximum. | Éviter que le journal devienne un relevé des heures d'utilisation. |
| D11 | Une seule main suivie par défaut (`num_hands = 1`) + verrouillage sur la main engagée (même côté, taille voisine, pas de saut). | Latence plus faible. Une autre main ne peut pas prendre le relais : elle doit refaire le geste d'engagement. |
| D12 | Point de pointage par défaut : centre de la paume (moyenne du poignet et des 4 bases de doigts). Option : base de l'index. | Stable quand on pince. |
| D13 | Choix de la caméra : automatique seulement s'il n'y a **qu'une** caméra utilisable (son nom figure dans l'écran d'accord) ; sinon choix obligatoire dans le menu. Les caméras dont le nom évoque l'infrarouge, Windows Hello ou la profondeur sont exclues. Sur le PC de test, la caméra infrarouge n'apparaît même pas dans les listes Media Foundation et DirectShow. | Choix explicite (3.5) sans étape inutile sur un portable à une seule webcam. |
| D14 | Écran d'accord minimal en phase 1 (boîte de dialogue Windows). | La règle 3.8 interdit d'allumer la caméra sans accord ; l'écran soigné en 3 étapes arrive en phase 3. |
| D15 | Petit témoin « caméra allumée » (iris de 28 px, toujours au premier plan, transparent aux clics) en bas à droite de l'écran principal. | Windows 11 range les icônes de notification dans un menu caché : l'indicateur doit rester visible (3.5). Il sera remplacé par la pastille en phase 3. |
| D16 | Les images ne sont pas retournées : seules les coordonnées le sont. L'étiquette « main gauche/droite » du modèle est donc inversée. | Moins de calcul. À confirmer physiquement. |
| D17 | Échange entre fils par un « emplacement » qui ne garde que la dernière image, tampons réutilisés et remis à zéro à l'arrêt. | Pas de file qui s'allonge ; les images sont écrasées. |
| D18 | Code dans `src/`, lancé par `SansContact.cmd` (sans installation du paquet). | Pas d'étape de construction. |
| D19 | Contrôle avant commit : les motifs personnels (nom, entreprise, lien privé) sont dans `.privacy-patterns.local`, ignoré par git. | Ne pas publier les données qu'on veut justement empêcher de publier. |
| D20 | Actions GitHub épinglées par empreinte de commit. | Sécurité de la chaîne d'approvisionnement. |
| D21 | Un témoin réseau au niveau du système : lecture des tables de connexions Windows pour notre processus (en plus du coupe-réseau Python). | Le code natif peut contourner Python ; ce témoin le voit. |
| D22 | `pywebview` vérifié sur Python 3.14.3 : fenêtre cachée, pont JavaScript fonctionnel, aucun port ouvert, compatible avec le coupe-réseau. | Lever le doute signalé en phase 0. Le contenu sera chargé sans serveur (chaîne HTML ou hôte virtuel WebView2). |
| D23 | (Sans objet depuis D4 : `tzdata`, `python-dateutil` et `matplotlib` ont été retirés avec MediaPipe.) | — |
