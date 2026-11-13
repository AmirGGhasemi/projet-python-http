# projet-python-http

Projet Répartition : **téléchargement HTTP P2P** en Python.

Ce dépôt contient pour l'instant l'**étape 1 : téléchargement HTTP**.
Un client télécharge un fichier depuis un serveur HTTP. Le client doit
fonctionner avec un serveur standard (Apache `httpd`), et notre serveur doit
fonctionner avec un navigateur web.

- Comment tester, avec les résultats attendus : voir [TESTS.md](TESTS.md)
- Diagrammes UML : voir le dossier [diagrammes/](diagrammes/)

---

## Démarrage rapide

Il faut Python 3 (aucune bibliothèque à installer, uniquement la bibliothèque standard).

```bash
# Terminal 1 : lancer notre serveur (partage le dossier "partage/" sur le port 8000)
python3 serveur.py 8000 partage

# Terminal 2 : télécharger un fichier avec notre client
python3 client.py localhost 8000 /exemple.txt
```

Puis ouvrir `http://localhost:8000/` dans un navigateur.
Le fichier téléchargé arrive dans `telechargements/`. Ctrl + C arrête le serveur.

| Commande | Arguments |
|----------|-----------|
| `python3 serveur.py [port] [dossier]` | par défaut : port `8000`, dossier `partage` |
| `python3 client.py hote port chemin [destination]` | par défaut, destination = `telechargements/<nom du fichier>` |

---

## Organisation des fichiers

```
projet-python-http/
├── http_commun.py   # outils partagés par le client et le serveur
├── client.py        # le client : télécharge un fichier (diagramme D2)
├── serveur.py       # le serveur : sert les fichiers d'un dossier (D3, D4, D5)
├── partage/         # dossier servi par défaut par notre serveur (exemple)
├── diagrammes/      # diagrammes UML D1 à D6
├── TESTS.md         # procédure de test
└── .gitignore       # ignore __pycache__/, telechargements/, .DS_Store
```

```
client.py ──── utilise ───┐                 ┌─── utilise ──── serveur.py
                          ▼                 ▼
                     http_commun.py (les outils partagés)
```

Le code suit le **diagramme de classes D6** : mêmes fichiers, mêmes classes,
mêmes noms de méthodes.

---

## Rappel : à quoi ressemble un échange HTTP

HTTP, c'est du **texte** envoyé sur une connexion **TCP**.
Chaque ligne se termine par `\r\n`, et une **ligne vide** (`\r\n\r\n`) sépare
les en-têtes du corps.

```
Requête (client -> serveur)          Réponse (serveur -> client)
---------------------------          ---------------------------
GET /test.txt HTTP/1.1               HTTP/1.1 200 OK
Host: localhost:8080                 Content-Type: text/plain
Connection: close                    Content-Length: 31
                                     
                                     Bonjour, ceci est un test HTTP
```

- `Host` est obligatoire en HTTP/1.1.
- `Connection: close` : le serveur ferme la connexion après la réponse
  (une requête = une connexion, c'est plus simple).
- `Content-Length` donne la taille du corps : c'est ce qui permet au client
  de savoir combien d'octets lire.

---

## `http_commun.py` : la boîte à outils partagée

| Classe | Rôle |
|--------|------|
| `ConnexionHTTP` | Enveloppe une socket TCP : lire les en-têtes, lire le corps, envoyer, fermer. |
| `RequeteHTTP` | Une requête (méthode, chemin, version, en-têtes). Conversion objet ↔ octets. |
| `ReponseHTTP` | Une réponse (code, raison, en-têtes, corps). Conversion objet ↔ octets, réponses d'erreur. |
| `ErreurHTTP` | Exception qui porte un code HTTP (400, 404, 405...). |

### `ConnexionHTTP` : le point le plus important

`sock.recv(4096)` ne renvoie **pas forcément un message complet** : il renvoie
ce qui est arrivé *pour l'instant*. Il faut donc lire en boucle.

- **`lire_entetes()`** lit en boucle jusqu'à trouver la ligne vide `\r\n\r\n`,
  puis coupe en deux : les en-têtes sont renvoyés, et **le reste est gardé dans
  `self.tampon`**. Le dernier `recv()` a pu ramener le début du fichier en
  même temps que la fin des en-têtes : sans le tampon, on perdrait ces octets.
- **`lire_corps(taille, fichier)`** écrit d'abord le contenu du tampon dans le
  fichier, puis continue les `recv()` jusqu'à avoir `taille` octets
  (`Content-Length`). Elle renvoie le nombre d'octets reçus : s'il est trop
  petit, la connexion a été coupée en route.
- **`envoyer()`** utilise `sendall()` (et pas `send()`), qui garantit que
  **tout** est envoyé.
- `TAILLE_BLOC = 4096` : on lit et on envoie par morceaux de 4 Ko.

### `RequeteHTTP` / `ReponseHTTP` : texte ↔ objets

Chacune a deux méthodes « miroir » :

- **`vers_octets()`** : objet → texte HTTP → bytes (pour **envoyer**)
- **`depuis_octets()`** : bytes → objet (pour **recevoir**). C'est une
  `@staticmethod` (le `{static}` du diagramme), car elle *fabrique* l'objet.

Découpage fait par `depuis_octets()` :

```
"GET /test.txt HTTP/1.1\r\nHost: localhost:8080"
          │ split("\r\n")
          ▼
["GET /test.txt HTTP/1.1", "Host: localhost:8080"]
  ligne 0          -> split(" ")    -> méthode, chemin, version
  lignes suivantes -> split(":", 1) -> nom, valeur
```

- `split(":", 1)` coupe au **premier** `:` seulement (sinon `localhost:8080` serait cassé).
- Les noms d'en-têtes sont mis en **minuscules** : en HTTP, `Content-Length` = `content-length`.
- Les en-têtes sont décodés en **ISO-8859-1** (l'encodage standard des en-têtes HTTP).
- Si le format est faux, on lève `ErreurHTTP(400)`.

`ReponseHTTP.erreur(code)` fabrique une petite page HTML d'erreur
(ex : « 404 Not Found ») que le navigateur affiche.
`taille_corps()` renvoie la valeur de `Content-Length` (ou `-1` si absent).

---

## `serveur.py` : le serveur (`ServeurHTTP`)

### Démarrer (diagramme D3)

1. `_verifier_dossier()` : le dossier partagé existe-t-il ? Sinon, on affiche « dossier introuvable » et on s'arrête.
2. `_creer_socket_ecoute()` :
   ```python
   sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # IPv4 + TCP
   sock.bind((hote, port))   # réserver le port
   sock.listen(5)            # commencer à écouter
   ```
   Si le port est déjà pris, `bind()` lève une `OSError` → « port indisponible ».
3. Boucle principale :
   ```python
   while self.en_marche:
       sock_client, adresse = self.socket_ecoute.accept()  # attend un client
       self._traiter_client(ConnexionHTTP(sock_client, adresse))
   ```
   La socket d'écoute sert seulement à « décrocher ». `accept()` crée une
   **nouvelle socket** dédiée à ce client. Les clients sont traités un par un.

### Servir un fichier (diagramme D5) : `_traiter_client()`

```python
try:
    requete = RequeteHTTP.depuis_octets(connexion.lire_entetes())  # 400 si mal formée
    if requete.methode != "GET": raise ErreurHTTP(405)              # 405
    fichier = self._chercher_fichier(requete.chemin)                # 400 ou 404
    self._envoyer_fichier(connexion, fichier)                       # 200
except ErreurHTTP as e:
    self._envoyer_erreur(connexion, e.code)   # un seul endroit gère toutes les erreurs
finally:
    connexion.fermer()                        # toujours exécuté
```

Chaque branche « Alternative » du diagramme D5 correspond à un `raise`.

| Méthode | Rôle |
|---------|------|
| `_chercher_fichier(chemin_url)` | Transforme l'URL en chemin sur le disque. Enlève `?...`, décode `%20` → espace, `/` → `/index.html`. **Sécurité** : `os.path.realpath()` résout les `..`, et si le chemin final sort du dossier partagé → 400. Fichier absent → 404. |
| `_type_mime(chemin)` | Donne le `Content-Type` selon l'extension (`.html`, `.png`, `.pdf`...). C'est ce qui permet au navigateur de savoir comment afficher le fichier. Par défaut : `application/octet-stream`. |
| `_envoyer_fichier(connexion, fichier)` | Envoie d'abord la ligne `200 OK` + les en-têtes (`Content-Type`, `Content-Length`, `Connection: close`), puis le fichier **bloc par bloc** (4 Ko) : un gros fichier n'est jamais chargé entièrement en mémoire. |
| `_envoyer_erreur(connexion, code)` | Envoie `ReponseHTTP.erreur(code)`. |

### Arrêter (diagramme D4)

Ctrl + C lève `KeyboardInterrupt` → `arreter()` passe `en_marche` à `False`
et ferme la socket d'écoute.

---

## `client.py` : le client (`ClientHTTP`)

`telecharger(chemin, destination)` suit le diagramme D2 de haut en bas :

| Étape | Méthode | En cas de problème |
|-------|---------|--------------------|
| 1. Se connecter | `_ouvrir_connexion()` → `socket.create_connection((hote, port), timeout=delai)` | « serveur injoignable » |
| 2. Envoyer `GET` | `_envoyer_requete()` → en-têtes `Host`, `User-Agent`, `Connection: close` | |
| 3. Lire la réponse | `_recevoir_reponse()` → `lire_entetes()` + `ReponseHTTP.depuis_octets()` | « réponse HTTP invalide » |
| 4. Vérifier le code | `reponse.code != 200` | « code d'erreur reçu : 404 Not Found » |
| 5. Lire la taille | `reponse.taille_corps()` | « Content-Length absent » |
| 6. Écrire le fichier | `_ecrire_fichier()` → `lire_corps()` dans un fichier ouvert en `"wb"` | « connexion interrompue » si reçus < taille |
| 7. Fermer | `connexion.fermer()` dans un `finally` | |

- Le fichier est ouvert en **binaire** (`"wb"`) : on écrit les octets tels quels,
  ça marche aussi bien pour un `.txt` que pour un `.pdf` ou une image.
- `delai` (10 s par défaut) évite d'attendre indéfiniment un serveur qui ne répond pas.
- Toutes les erreurs sont transformées en `ErreurTelechargement`, affichée proprement
  dans le terminal.

---

## Écarts mineurs avec le diagramme de classes (D6)

- Une méthode d'aide privée en plus : `RequeteHTTP._lire_lignes_entetes()`,
  réutilisée par `ReponseHTTP` pour ne pas écrire deux fois le découpage des en-têtes.
- Les attributs gardent les noms exacts du diagramme (`code`, `chemin`...),
  sans préfixe `_`, car d'autres classes les lisent (ex : `reponse.code` dans D2).
- `RequeteHTTP.__init__` ne reçoit pas la version : elle vaut `"HTTP/1.1"` par
  défaut et `depuis_octets()` la remplace par celle reçue.
