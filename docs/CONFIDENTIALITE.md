# Confidentialité — SansContact

Version de travail (phase 1). Ce document est écrit pour être lu par une personne non technique,
et pour servir de base à un échange avec le délégué à la protection des données (DPO).

## En une phrase

L'image de la caméra ne quitte jamais la mémoire de l'ordinateur et ne sert qu'à déplacer le curseur.

## Ce que fait la caméra

- Elle filme la main placée devant l'écran, en basse résolution (640 × 480 par défaut).
- Elle n'est allumée que lorsque vous activez l'outil. Au lancement, l'outil est toujours désactivé.
- La caméra infrarouge de Windows Hello n'est jamais utilisée.
- Un petit témoin en forme d'iris reste visible en bas à droite de l'écran tant que la caméra est allumée.
  Le voyant de la caméra n'est jamais masqué.

## Ce qui est calculé

- 21 points de la main (les articulations), recalculés à chaque image, uniquement pour placer le curseur.
- En mode main, aucun visage n'est recherché.
- Rien d'autre : pas de reconnaissance de la personne, pas de comparaison entre personnes, pas d'estimation
  de l'âge, du genre, de l'origine, des émotions, de la fatigue ou de l'attention, aucune mesure d'activité.
- Si plusieurs mains sont visibles, seule celle qui a fait le geste de prise de contrôle compte.
  Les autres sont ignorées et leurs données jetées aussitôt.

## Ce qui n'est jamais conservé ni envoyé

- Aucune image n'est enregistrée, affichée ou transmise. Les images sont traitées en mémoire,
  puis la mémoire utilisée est écrasée.
- Aucune connexion réseau : l'application coupe tout accès réseau à son démarrage et compte les
  tentatives. Le compteur est affiché dans l'infobulle de l'icône et doit rester à 0.
- Le journal technique ne contient que des chiffres (images par seconde, délais, processeur, mémoire,
  nombre de clics et de gestes reconnus), sans date ni heure, sans position du curseur, sans titre de
  fenêtre ni nom de fichier.
- Pour que le clic tombe au bon endroit, les positions du curseur des deux dernières secondes sont gardées
  en mémoire, jamais écrites, et effacées à chaque arrêt.

## Ce qui est stocké sur l'ordinateur

Uniquement dans `%LOCALAPPDATA%\SansContact\` (jamais dans Documents, sur le Bureau ou dans OneDrive) :

| Fichier | Contenu |
|---|---|
| `settings.json` | Réglages chiffrés (caméra choisie, résolution, sensibilité…). |
| `consent.json` | Le numéro de version de l'explication que vous avez acceptée (pas de date). |
| `metrics.log` | Journal technique chiffré, 512 Ko au plus. |

## Comment tout arrêter

- Raccourci clavier `Ctrl + Alt + Maj + Espace` (fonctionne toujours, même si la main n'est plus vue).
- Un clic sur l'icône SansContact dans la zone de notification.
- La souris physique reprend la main automatiquement : si vous la bougez, le pilotage se met en pause.
- Verrouiller la session, mettre en veille ou éteindre l'écran libère la caméra immédiatement.

## Comment tout supprimer

Clic droit sur l'icône › « Supprimer toutes mes données ». La caméra s'éteint et le dossier
`%LOCALAPPDATA%\SansContact\` est supprimé.

## Pourquoi SansContact n'utilise pas la bibliothèque MediaPipe

La bibliothèque MediaPipe de Google (version 1.1.1) contient un module de statistiques d'usage capable
d'envoyer des données sur Internet (adresse `play.googleapis.com/log`). C'est contraire à la règle
« aucune connexion réseau ». SansContact ne l'utilise donc pas, et elle n'est même pas installée :

- les modèles de détection de la main (des fichiers de calcul, sans code, publiés sous licence Apache-2.0
  par le projet OpenCV) sont exécutés par OpenCV, une bibliothèque d'analyse d'image. OpenCV sait lire des
  vidéos sur Internet, mais SansContact ne lui donne jamais d'adresse : seulement le numéro de la caméra ;
- le traitement autour de ces modèles (recadrage, suivi de la main d'une image à l'autre) est écrit dans
  SansContact, d'après les paramètres publiés par MediaPipe ;
- un test automatique échoue si MediaPipe ou une bibliothèque audio, de graphiques ou de certificats web
  est réinstallée par erreur.

Les modes tête et regard suivront la même règle pour les modèles du visage.

Les fichiers des modèles sont vérifiés (empreinte numérique) avant chaque allumage de la caméra : un
fichier modifié est refusé et la caméra reste éteinte.

## Bloquer soi-même les connexions sortantes (facultatif)

SansContact ne modifie jamais le pare-feu. Si vous voulez une garantie supplémentaire, vous pouvez
créer vous-même une règle qui interdit toute connexion sortante au programme Python de SansContact.
Il faut une invite de commandes **ouverte en administrateur** ; sur un PC d'entreprise, le service
informatique peut l'interdire ou ignorer les règles locales.

```bat
netsh advfirewall firewall add rule name="SansContact - aucune connexion sortante" dir=out action=block program="CHEMIN\VERS\sanscontact\.venv\Scripts\pythonw.exe" enable=yes
netsh advfirewall firewall add rule name="SansContact - aucune connexion sortante (console)" dir=out action=block program="CHEMIN\VERS\sanscontact\.venv\Scripts\python.exe" enable=yes
```

Remplacez `CHEMIN\VERS` par l'emplacement du dossier. Pour retirer ces règles :

```bat
netsh advfirewall firewall delete rule name="SansContact - aucune connexion sortante"
netsh advfirewall firewall delete rule name="SansContact - aucune connexion sortante (console)"
```

## Limites connues (phase 1)

- La mémoire interne utilisée par la bibliothèque de détection est libérée à l'arrêt, mais nous ne
  pouvons pas garantir qu'elle soit effacée octet par octet : seuls nos propres tampons le sont.
- Le témoin réseau lit les connexions ouvertes par SansContact toutes les 250 ms : une connexion très brève
  pourrait lui échapper. La règle de pare-feu ci-dessus donne une garantie plus forte.
