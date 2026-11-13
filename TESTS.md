# Tests de l'étape 1 : téléchargement HTTP

Ce document liste les tests à faire pour vérifier le client et le serveur,
avec le résultat attendu pour chacun. Toutes les commandes se lancent
**depuis le dossier du repo** (`projet-python-http/`).

Il faut **deux terminaux** : un pour le serveur, un pour le client.

---

## 0. Préparation (une seule fois)

### 0.1 Récupérer le code

```bash
git checkout main
git pull
```

### 0.2 Lancer le serveur Apache (httpd) dans Docker

Le sujet demande que notre client fonctionne avec un **serveur HTTP standard**.
On utilise l'image officielle `httpd` d'Apache.

1. Installer et lancer **Docker Desktop**.
2. Créer un dossier **en dehors du repo** pour les fichiers qu'Apache va servir,
   et y mettre un fichier de test :

   ```bash
   mkdir -p ../public-html
   echo "Bonjour, ceci est un test HTTP" > ../public-html/test.txt
   ```

3. Lancer le conteneur (port 8080 de la machine -> port 80 d'Apache) :

   ```bash
   docker run -dit --name serveur-httpd -p 8080:80 -v "$(cd ../public-html && pwd)":/usr/local/apache2/htdocs/ httpd:2.4
   ```

   > Attention : n'exposez **que** ce dossier dédié, jamais votre dossier personnel.

4. Vérifier : ouvrir `http://localhost:8080/` dans un navigateur, on doit voir `test.txt`.

Commandes utiles : `docker stop serveur-httpd`, `docker start serveur-httpd`,
`docker logs -f serveur-httpd` (affiche les requêtes reçues).

---

## Test 1 : notre client contre httpd (Apache)

| # | Commande | Résultat attendu |
|---|----------|------------------|
| 1.1 | `python3 client.py localhost 8080 /test.txt` | `Téléchargement terminé : telechargements/test.txt (31 octets)` |
| 1.2 | `cat telechargements/test.txt` | `Bonjour, ceci est un test HTTP` |
| 1.3 | `python3 client.py localhost 8080 /nexistepas.txt` | `Échec du téléchargement : code d'erreur reçu : 404 Not Found` |
| 1.4 | `python3 client.py localhost 8999 /test.txt` (port où rien n'écoute) | `Échec du téléchargement : serveur injoignable` |

Ce que ça prouve : le client sait parler à un vrai serveur HTTP, et il gère
les cas d'erreur du diagramme D2 (404, serveur injoignable).

---

## Test 2 : notre serveur avec un navigateur

**Terminal 1** : lancer le serveur (il reste bloqué tant qu'il tourne, c'est normal) :

```bash
python3 serveur.py 8000 partage
```

Résultat attendu :

```
Serveur en écoute sur le port 8000 - dossier partagé : .../projet-python-http/partage
Ctrl + C pour arrêter.
```

Dans le **navigateur** (Safari, Chrome...) :

| # | URL | Résultat attendu |
|---|-----|------------------|
| 2.1 | `http://localhost:8000/` | Page « Notre serveur HTTP fonctionne » avec un lien |
| 2.2 | `http://localhost:8000/exemple.txt` | Le texte « Bonjour ! Ce fichier est servi par notre serveur Python. » |
| 2.3 | `http://localhost:8000/nimportequoi` | Page « 404 Not Found » |
| 2.4 | Copier une image ou un PDF dans `partage/`, puis l'ouvrir via `http://localhost:8000/<nom du fichier>` | Le navigateur affiche l'image ou le PDF |

Dans le terminal 1, chaque requête s'affiche, par exemple :

```
127.0.0.1 -> GET /exemple.txt
127.0.0.1 -> GET /nimportequoi
   erreur 404
```

> Le navigateur demande aussi souvent `/favicon.ico` (l'icône de l'onglet) :
> une erreur 404 sur ce fichier est normale.

Ce que ça prouve : notre serveur est compatible avec un navigateur web (diagramme D5).

---

## Test 3 : notre client contre notre serveur

Laisser le serveur tourner dans le terminal 1. Dans le **terminal 2** :

| # | Commande | Résultat attendu |
|---|----------|------------------|
| 3.1 | `python3 client.py localhost 8000 /exemple.txt` | `Téléchargement terminé : telechargements/exemple.txt (57 octets)` |
| 3.2 | `head -c 5000000 /dev/urandom > partage/gros.bin` | (crée un fichier aléatoire de 5 Mo) |
| 3.3 | `python3 client.py localhost 8000 /gros.bin` | `Téléchargement terminé : telechargements/gros.bin (5000000 octets)` |
| 3.4 | `cmp partage/gros.bin telechargements/gros.bin && echo "IDENTIQUE"` | `IDENTIQUE` |

> Après le test, supprimer `partage/gros.bin` pour ne pas le commiter :
> `rm partage/gros.bin`

Ce que ça prouve : un gros fichier binaire arrive **intact**, octet par octet
(lecture par blocs et gestion du tampon correctes).

---

## Test 4 : les erreurs du serveur (avec curl)

Le serveur tourne toujours dans le terminal 1. Dans le **terminal 2** :

| # | Commande | Résultat attendu (1re ligne) |
|---|----------|------------------------------|
| 4.1 | `curl -i http://localhost:8000/exemple.txt` | `HTTP/1.1 200 OK` + en-têtes `Content-Type`, `Content-Length: 57` |
| 4.2 | `curl -i -X POST http://localhost:8000/exemple.txt` | `HTTP/1.1 405 Method Not Allowed` |
| 4.3 | `curl -i --path-as-is http://localhost:8000/../serveur.py` | `HTTP/1.1 400 Bad Request` (interdit de sortir du dossier partagé) |
| 4.4 | `printf 'BONJOUR\r\n\r\n' \| nc localhost 8000` | `HTTP/1.1 400 Bad Request` (requête mal formée) |
| 4.5 | `curl -i http://localhost:8000/absent.txt` | `HTTP/1.1 404 Not Found` |

Ce que ça prouve : toutes les branches d'erreur du diagramme D5 (400, 404, 405)
fonctionnent, ainsi que la protection contre l'accès à des fichiers hors du dossier partagé.

---

## Test 5 : démarrage et arrêt du serveur

| # | Action | Résultat attendu |
|---|--------|------------------|
| 5.1 | Dans le terminal 1, appuyer sur **Ctrl + C** | `Serveur arrêté.` (diagramme D4) |
| 5.2 | `python3 serveur.py 8080 partage` (port déjà pris par httpd) | `Erreur : port 8080 indisponible : [Errno ...] Address already in use` (48 sur macOS, 98 sur Linux) |
| 5.3 | `python3 serveur.py 8000 dossier_absent` | `Erreur : dossier introuvable : dossier_absent` |

Ce que ça prouve : les cas d'erreur au démarrage du diagramme D3 sont gérés.

---

## Problèmes fréquents

| Problème | Cause / solution |
|----------|------------------|
| `Address already in use` sur le port 8000 | Un ancien serveur tourne encore : Ctrl + C dans son terminal, ou utiliser un autre port (`python3 serveur.py 8001 partage`). |
| Le client vers le port 8080 dit « serveur injoignable » | Le conteneur Docker est arrêté : `docker start serveur-httpd`. |
| `python3: command not found` | Installer Python 3 (sur Windows, la commande est souvent `python` ou `py`). |
| `cmp` ou `nc` introuvable (Windows) | Faire ces tests sous macOS / Linux / WSL, ou les sauter. |

---

## Pour la vidéo de rendu

Enchaîner les tests 1 à 5 dans cet ordre donne une démonstration complète :
client contre Apache, serveur dans le navigateur, client contre notre serveur,
gestion des erreurs, puis démarrage et arrêt.
