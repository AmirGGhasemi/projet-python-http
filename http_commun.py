"""
http_commun.py
==============
Classes partagées par le client (client.py) et le serveur (serveur.py).

Rappel : un message HTTP est du TEXTE envoyé sur une connexion TCP.

    Requête (client -> serveur)          Réponse (serveur -> client)
    ---------------------------          ---------------------------
    GET /test.txt HTTP/1.1\r\n           HTTP/1.1 200 OK\r\n
    Host: localhost:8080\r\n             Content-Type: text/plain\r\n
    Connection: close\r\n                Content-Length: 31\r\n
    \r\n                                 \r\n
                                         Bonjour, ceci est un test HTTP

Chaque ligne se termine par "\r\n". Une ligne vide ("\r\n\r\n") sépare
les en-têtes du corps.

Contenu du module (voir le diagramme de classes D6) :
    - ErreurHTTP    : exception portant un code d'erreur HTTP (400, 404...)
    - ConnexionHTTP : enveloppe une socket, lit les en-têtes / le corps
    - RequeteHTTP   : représente une requête (méthode, chemin, en-têtes)
    - ReponseHTTP   : représente une réponse (code, en-têtes, corps)
"""

# Séparateur de lignes imposé par le protocole HTTP.
FIN_LIGNE = "\r\n"
# Ligne vide qui marque la fin des en-têtes.
FIN_ENTETES = b"\r\n\r\n"
# Les en-têtes HTTP sont encodés en ISO-8859-1 (latin-1), pas en UTF-8.
ENCODAGE_ENTETES = "iso-8859-1"


class ErreurHTTP(Exception):
    """Erreur qui correspond à un code HTTP (ex : 400, 404, 405).

    Le serveur lève cette exception quand quelque chose ne va pas, puis
    l'attrape pour renvoyer la bonne réponse d'erreur au client.
    """

    def __init__(self, code, message=""):
        # On appelle le constructeur de Exception pour garder le message.
        super().__init__(message)
        self.code = code


class ConnexionHTTP:
    """Une connexion TCP ouverte avec l'autre machine.

    Sert des deux côtés :
      - côté serveur, elle est créée après socket.accept()
      - côté client, elle est créée après la connexion au serveur
    """

    # Taille des morceaux lus ou envoyés en une fois (4 Ko).
    TAILLE_BLOC = 4096

    def __init__(self, sock, adresse):
        self.sock = sock          # la socket TCP déjà connectée
        self.adresse = adresse    # (ip, port) de l'autre machine
        # Le tampon garde les octets déjà reçus mais pas encore utilisés.
        # Pourquoi ? Avec recv() on peut recevoir la fin des en-têtes ET
        # le début du corps en même temps : il ne faut pas les perdre.
        self.tampon = b""

    def lire_entetes(self):
        """Lit la socket jusqu'à la ligne vide et renvoie les en-têtes (bytes).

        Le résultat contient la première ligne + les en-têtes, sans la
        ligne vide finale. Ce qui a été reçu en trop (début du corps) reste
        dans self.tampon pour lire_corps().
        """
        # On lit tant que la ligne vide "\r\n\r\n" n'est pas arrivée.
        while FIN_ENTETES not in self.tampon:
            morceau = self.sock.recv(self.TAILLE_BLOC)
            if not morceau:
                # recv() renvoie b"" quand l'autre côté a fermé la connexion.
                raise ErreurHTTP(400, "connexion fermée avant la fin des en-têtes")
            self.tampon += morceau

        # On coupe en deux au niveau de la ligne vide.
        entetes, reste = self.tampon.split(FIN_ENTETES, 1)
        self.tampon = reste  # le début du corps éventuel
        return entetes

    def lire_corps(self, taille, fichier):
        """Lit `taille` octets de corps et les écrit dans `fichier`.

        `fichier` est un fichier ouvert en écriture binaire ("wb").
        Renvoie le nombre d'octets réellement reçus : s'il est plus petit
        que `taille`, la connexion a été coupée en route.
        """
        recus = 0

        # 1) D'abord les octets déjà présents dans le tampon.
        if self.tampon:
            debut = self.tampon[:taille]
            fichier.write(debut)
            recus += len(debut)
            self.tampon = self.tampon[len(debut):]

        # 2) Puis on lit la socket jusqu'à avoir tout reçu.
        while recus < taille:
            # On ne demande jamais plus que ce qu'il reste à lire.
            a_lire = min(self.TAILLE_BLOC, taille - recus)
            morceau = self.sock.recv(a_lire)
            if not morceau:
                break  # connexion fermée : on s'arrête
            fichier.write(morceau)
            recus += len(morceau)

        return recus

    def envoyer(self, donnees):
        """Envoie des octets sur la connexion.

        sendall() (et pas send()) garantit que TOUT est envoyé, même si
        le système doit le faire en plusieurs fois.
        """
        self.sock.sendall(donnees)

    def fermer(self):
        """Ferme la connexion TCP."""
        self.sock.close()


class RequeteHTTP:
    """Une requête HTTP, par exemple : GET /test.txt HTTP/1.1"""

    def __init__(self, methode, chemin, entetes):
        self.methode = methode      # "GET", "POST"...
        self.chemin = chemin        # "/test.txt"
        self.version = "HTTP/1.1"   # version du protocole
        self.entetes = entetes      # dict, ex : {"Host": "localhost:8080"}

    @staticmethod
    def depuis_octets(donnees):
        """Construit une RequeteHTTP à partir des octets reçus (côté serveur).

        `donnees` = ce que renvoie ConnexionHTTP.lire_entetes().
        Lève ErreurHTTP(400) si la requête est mal formée.
        """
        texte = donnees.decode(ENCODAGE_ENTETES)
        lignes = texte.split(FIN_LIGNE)

        # Première ligne : "MÉTHODE CHEMIN VERSION"
        morceaux = lignes[0].split(" ")
        if len(morceaux) != 3:
            raise ErreurHTTP(400, "ligne de requête invalide")
        methode, chemin, version = morceaux
        if not version.startswith("HTTP/"):
            raise ErreurHTTP(400, "version HTTP invalide")

        # Lignes suivantes : "Nom: valeur"
        entetes = RequeteHTTP._lire_lignes_entetes(lignes[1:])

        requete = RequeteHTTP(methode, chemin, entetes)
        requete.version = version
        return requete

    @staticmethod
    def _lire_lignes_entetes(lignes):
        """Transforme ["Host: a", "Accept: b"] en {"host": "a", "accept": "b"}.

        Les noms d'en-têtes ne sont pas sensibles à la casse en HTTP
        ("Content-Length" == "content-length"), donc on les met en minuscules.
        """
        entetes = {}
        for ligne in lignes:
            if ":" not in ligne:
                raise ErreurHTTP(400, "en-tête invalide : " + ligne)
            # split(":", 1) coupe au PREMIER ":" seulement
            # (utile pour "Host: localhost:8080").
            nom, valeur = ligne.split(":", 1)
            entetes[nom.strip().lower()] = valeur.strip()
        return entetes

    def vers_octets(self):
        """Transforme la requête en octets prêts à être envoyés (côté client)."""
        texte = self.methode + " " + self.chemin + " " + self.version + FIN_LIGNE
        for nom, valeur in self.entetes.items():
            texte += nom + ": " + valeur + FIN_LIGNE
        texte += FIN_LIGNE  # ligne vide = fin des en-têtes
        return texte.encode(ENCODAGE_ENTETES)


class ReponseHTTP:
    """Une réponse HTTP, par exemple : HTTP/1.1 200 OK"""

    # Texte associé à chaque code de statut utilisé dans le projet.
    RAISONS = {
        200: "OK",
        400: "Bad Request",
        404: "Not Found",
        405: "Method Not Allowed",
        500: "Internal Server Error",
    }

    def __init__(self, code, entetes, corps=b""):
        self.version = "HTTP/1.1"
        self.code = code
        self.raison = self.RAISONS.get(code, "Unknown")
        self.entetes = entetes
        self.corps = corps

    @staticmethod
    def depuis_octets(donnees):
        """Construit une ReponseHTTP à partir des octets reçus (côté client).

        `donnees` = ce que renvoie ConnexionHTTP.lire_entetes().
        Le corps n'est PAS lu ici : il est écrit directement dans un fichier
        par ConnexionHTTP.lire_corps().
        """
        texte = donnees.decode(ENCODAGE_ENTETES)
        lignes = texte.split(FIN_LIGNE)

        # Première ligne : "HTTP/1.1 200 OK"
        # split(" ", 2) -> 3 morceaux max, car la raison peut contenir
        # des espaces ("Not Found").
        morceaux = lignes[0].split(" ", 2)
        if len(morceaux) < 2 or not morceaux[1].isdigit():
            raise ErreurHTTP(400, "ligne de statut invalide")

        code = int(morceaux[1])
        entetes = RequeteHTTP._lire_lignes_entetes(lignes[1:])

        reponse = ReponseHTTP(code, entetes)
        reponse.version = morceaux[0]
        if len(morceaux) == 3:
            reponse.raison = morceaux[2]  # on garde le texte envoyé par le serveur
        return reponse

    @staticmethod
    def erreur(code):
        """Fabrique une réponse d'erreur avec une petite page HTML."""
        raison = ReponseHTTP.RAISONS.get(code, "Unknown")
        corps = ("<html><body><h1>" + str(code) + " " + raison
                 + "</h1></body></html>").encode("utf-8")
        entetes = {
            "Content-Type": "text/html; charset=utf-8",
            "Content-Length": str(len(corps)),
            "Connection": "close",
        }
        return ReponseHTTP(code, entetes, corps)

    def vers_octets(self):
        """Transforme la réponse en octets prêts à être envoyés (côté serveur)."""
        texte = self.version + " " + str(self.code) + " " + self.raison + FIN_LIGNE
        for nom, valeur in self.entetes.items():
            texte += nom + ": " + valeur + FIN_LIGNE
        texte += FIN_LIGNE  # ligne vide = fin des en-têtes
        return texte.encode(ENCODAGE_ENTETES) + self.corps

    def taille_corps(self):
        """Renvoie la valeur de Content-Length, ou -1 si l'en-tête est absent."""
        for nom, valeur in self.entetes.items():
            if nom.lower() == "content-length":
                return int(valeur)
        return -1
