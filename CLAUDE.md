# SansContact — règles pour chaque session

Ce fichier est publié. Il ne contient aucun chemin local ni information personnelle.
Code, noms et commentaires en anglais ; interface, messages et documentation en français.

## Vie privée et protection de la personne (non négociable)

Principe : l'image d'une personne ne quitte jamais la mémoire vive et ne sert qu'à déplacer un curseur.
En cas de conflit entre une fonctionnalité et ces règles, les règles gagnent : signale le conflit, ne le contourne pas.

### Traitement 100 % local
- N'ouvre aucune connexion réseau pendant l'exécution. N'importe aucune bibliothèque réseau dans le code d'exécution.
- N'ouvre aucun serveur ni port, même sur `127.0.0.1` : pas de WebSocket, pas d'API HTTP locale. Le pont pywebview suffit.
- L'interface ne fait aucune requête externe : polices embarquées, aucun CDN, CSP limitée à `'self'`, navigation externe bloquée.
- Installe le coupe-réseau (`privacy/network_guard.py`) avant tout autre import au démarrage. Le compteur de connexions doit rester à 0.
- Signale toute dépendance ou fonction qui contacte Internet, et documente-la honnêtement.

### Aucune image conservée
- Traite les images en mémoire, puis écrase les tampons. N'écris jamais une image sur disque, en cache, dans un journal ou un rapport d'erreur.
- N'affiche jamais les variables locales dans une trace d'erreur (`capture_locals`/`show_locals` interdits).
- Aucune capture d'écran, aucun enregistrement vidéo, aucun bouton « enregistrer », même en débogage.
- Retour visuel : squelette ou points dessinés à partir des coordonnées, jamais l'image de la caméra.
- Aperçu caméra réel : désactivé par défaut, affichage seul, fenêtre exclue des captures (`WDA_EXCLUDEFROMCAPTURE`).
- Les tests utilisent des séquences de points synthétiques, jamais l'enregistrement d'une vraie personne.

### Minimisation
- Mode main : aucune détection de visage. Modes tête et regard : pas de détection de main, sauf mode hybride.
- Résolution de caméra la plus basse qui donne de bons résultats. N'extrais que les points nécessaires.
- Interdits absolus : identifier ou reconnaître une personne ; comparer des visages ou des mains ; déduire âge, genre, origine, émotions, fatigue, attention ou humeur ; mesurer l'activité ou la productivité.
- Les expressions du visage ne servent que de commandes volontaires, lues en direct, jamais stockées, jamais présentées comme un état de la personne.

### Personnes autour
- Seule la personne qui a fait le geste d'engagement contrôle. Toute autre main est ignorée et ses données jetées aussitôt.
- Modes tête et regard : suivre le visage le plus proche ; si le visage suivi semble changer, mettre en pause.

### Cycle de vie de la caméra
- Caméra allumée seulement quand l'outil est activé ; libérée après 30 s de pause (réglable).
- Libération immédiate à la désactivation, au verrouillage de session, à la mise en veille, au changement d'utilisateur, à la fermeture et en cas d'erreur (`try/finally`).
- Indicateur toujours visible quand la caméra est allumée. Ne jamais masquer le voyant de la caméra.
- Au lancement, l'outil est toujours désactivé. Pas de démarrage automatique avec Windows par défaut.
- Choix explicite de la caméra. Ne jamais utiliser une caméra infrarouge (Windows Hello).

### Journaux et données stockées
- Journaux : métriques techniques agrégées uniquement (fps, latence, CPU, nombre de gestes), sans date ni heure.
- Jamais dans les journaux : positions du curseur ou du regard, titres de fenêtres, noms de fichiers, contenu de l'écran.
- Stockage uniquement dans `%LOCALAPPDATA%\SansContact\`, jamais dans Documents, sur le Bureau ou dans OneDrive.
- Calibration : coefficients numériques seulement, jamais les échantillons. Un profil par compte Windows.
- « Supprimer toutes mes données » doit tout effacer ; la désinstallation ne laisse rien.

### Sécurité des actions
- Pas de frappe clavier simulée par défaut ; seulement une liste blanche de raccourcis activés explicitement.
- Raccourcis globaux par `RegisterHotKey`. Jamais de hook clavier ni de hook souris.
- La souris physique est prioritaire : si le curseur n'est pas où l'application l'a mis, pause automatique (`GetCursorPos`).
- Aucun bouton ne reste enfoncé : tout relâcher à la pause, à la désactivation, à la sortie et en cas d'erreur.
- Le raccourci de désactivation fonctionne toujours ; sortir la main du champ désengage après quelques secondes.
- Fonctionner sans droits administrateur. Détecter les fenêtres protégées (UIPI) et prévenir, sans jamais proposer de lancer l'application en administrateur.

### Transparence et consentement
- La caméra ne s'allume pas sans acceptation de l'écran d'explication (ce qui est filmé, calculé, jamais conservé, comment tout arrêter et tout supprimer).
- `docs/CONFIDENTIALITE.md` reste lisible par une personne non technique.

### Protection physique et inclusion
- Zone active réduite et gain réglable, pour piloter le coude posé. Tout est configurable (main, amplitude, durées, sensibilité).
- Clic par maintien disponible mais désactivé par défaut.
- Tester et documenter la détection selon la couleur de peau, l'éclairage, les bagues, les manches. Signaler les écarts.
- Aucun clignotement de plus de 3 fois par seconde.

## Façon de travailler
- Ne capture et ne regarde jamais une image de la caméra ou de l'écran. Seule exception : l'interface en mode démo (données fictives, sans caméra).
- Vérifie par des métriques chiffrées et des tests sur données synthétiques. Distingue ce qui est vérifié automatiquement de ce que l'utilisateur doit tester physiquement.
- Demande avant d'installer quoi que ce soit (paquet, rôle, licence). Versions épinglées avec empreintes.
- Ne modifie jamais les paramètres système ou de sécurité de Windows. Ne lance rien en administrateur. Si une politique de sécurité bloque quelque chose, arrête-toi et explique.
- Rien n'est publié sans accord explicite : pas de dépôt distant, pas de `push`, pas de GitHub Pages avant la liste `docs/PUBLICATION.md`.
- Note dans `docs/DECISIONS.md` toute décision prise sans l'utilisateur.
- Le contrôle avant commit (`scripts/privacy_check.py`) ne doit jamais être contourné.
