"""
serveur.py
==========
Serveur HTTP minimal : il partage les fichiers d'un dossier.
Il doit fonctionner avec un navigateur web (Safari, Chrome...) et avec
notre client (client.py).

Utilisation :
    python3 serveur.py [port] [dossier_partage]
Exemple :
    python3 serveur.py 8000 partage
Puis ouvrir http://localhost:8000/exemple.txt dans le navigateur.
Arrêt : Ctrl + C

Diagrammes correspondants : D3 (démarrer), D4 (arrêter), D5 (servir un fichier).
"""

import os
import socket
import sys
from urllib.parse import unquote

from http_commun import ConnexionHTTP, ErreurHTTP, ReponseHTTP, RequeteHTTP


class ServeurHTTP:
    """Serveur qui envoie les fichiers d'un dossier en HTTP."""

    # Type MIME (Content-Type) selon l'extension du fichier.
    # Il dit au navigateur comment afficher le fichier.
    TYPES_MIME = {
        ".html": "text/html; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
        ".css": "text/css",
        ".js": "application/javascript",
        ".json": "application/json",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".pdf": "application/pdf",
        ".mp4": "video/mp4",
        ".zip": "application/zip",
    }

    def __init__(self, port, dossier_partage, hote=""):
        self.hote = hote                        # "" = toutes les interfaces réseau
        self.port = port                        # ex : 8000
        self.dossier_partage = dossier_partage  # dossier dont on partage les fichiers
        self.socket_ecoute = None               # créée dans demarrer()
        self.en_marche = False

    # ------------------------------------------------------------------
    # Méthodes publiques
    # ------------------------------------------------------------------

    def demarrer(self):
        """Démarre le serveur puis traite les clients un par un (D3)."""
        # 1) Le dossier partagé existe-t-il ?
        if not self._verifier_dossier():
            print("Erreur : dossier introuvable :", self.dossier_partage)
            return

        # 2) Création de la socket d'écoute (peut échouer si le port est pris).
        try:
            self.socket_ecoute = self._creer_socket_ecoute()
        except OSError as e:
            print("Erreur : port", self.port, "indisponible :", e)
            return

        self.en_marche = True
        print("Serveur en écoute sur le port", self.port,
              "- dossier partagé :", os.path.abspath(self.dossier_partage))
        print("Ctrl + C pour arrêter.")

        # 3) Boucle principale : on attend un client, on le sert, on recommence.
        try:
            while self.en_marche:
                # accept() BLOQUE jusqu'à ce qu'un client se connecte.
                # Il renvoie une NOUVELLE socket dédiée à ce client.
                sock_client, adresse = self.socket_ecoute.accept()
                connexion = ConnexionHTTP(sock_client, adresse)
                self._traiter_client(connexion)
        except KeyboardInterrupt:
            # Ctrl + C dans le terminal (D4)
            print()
        finally:
            self.arreter()

    def arreter(self):
        """Arrête le serveur (D4)."""
        self.en_marche = False
        if self.socket_ecoute is not None:
            self.socket_ecoute.close()
            self.socket_ecoute = None
            print("Serveur arrêté.")

    # ------------------------------------------------------------------
    # Méthodes privées (préfixe _)
    # ------------------------------------------------------------------

    def _verifier_dossier(self):
        """Renvoie True si le dossier partagé existe."""
        return os.path.isdir(self.dossier_partage)

    def _creer_socket_ecoute(self):
        """Crée la socket qui attend les connexions des clients."""
        # AF_INET = IPv4, SOCK_STREAM = TCP
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Permet de relancer le serveur tout de suite après l'avoir arrêté
        # (sinon : "Address already in use" pendant quelques secondes).
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.hote, self.port))  # on réserve le port
        sock.listen(5)                     # on commence à écouter
        return sock

    def _traiter_client(self, connexion):
        """Lit la requête d'un client et lui envoie la réponse (D5)."""
        try:
            # 1) Lire et analyser la requête
            octets = connexion.lire_entetes()
            requete = RequeteHTTP.depuis_octets(octets)
            print(connexion.adresse[0], "->", requete.methode, requete.chemin)

            # 2) On n'accepte que GET
            if requete.methode != "GET":
                raise ErreurHTTP(405, "méthode non autorisée")

            # 3) Trouver le fichier puis l'envoyer
            fichier = self._chercher_fichier(requete.chemin)
            self._envoyer_fichier(connexion, fichier)

        except ErreurHTTP as e:
            # Toutes les erreurs "prévues" (400, 404, 405) arrivent ici.
            print("   erreur", e.code)
            self._envoyer_erreur(connexion, e.code)
        except OSError as e:
            # Le client a coupé la connexion en plein milieu : rien à faire.
            print("   connexion interrompue :", e)
        finally:
            # Dans tous les cas, on ferme la connexion (Connection: close).
            connexion.fermer()

    def _chercher_fichier(self, chemin_url):
        """Transforme le chemin de l'URL en chemin sur le disque.

        Ex : "/images/chat%20noir.png" -> "partage/images/chat noir.png"
        Lève ErreurHTTP(400) si le chemin sort du dossier partagé,
        et ErreurHTTP(404) si le fichier n'existe pas.
        """
        # On enlève les paramètres éventuels : "/a.txt?x=1" -> "/a.txt"
        chemin_url = chemin_url.split("?")[0]
        # Les navigateurs encodent certains caractères : "%20" -> " "
        chemin_url = unquote(chemin_url)

        if chemin_url == "/":
            chemin_url = "/index.html"

        # Chemin complet sur le disque.
        # realpath() résout les ".." : "partage/../secret" -> "/.../secret"
        dossier = os.path.realpath(self.dossier_partage)
        chemin = os.path.realpath(os.path.join(dossier, chemin_url.lstrip("/")))

        # SÉCURITÉ : interdit de sortir du dossier partagé (ex : /../../etc/passwd)
        if not chemin.startswith(dossier + os.sep):
            raise ErreurHTTP(400, "chemin interdit")

        if not os.path.isfile(chemin):
            raise ErreurHTTP(404, "fichier introuvable")

        return chemin

    def _type_mime(self, chemin_fichier):
        """Renvoie le Content-Type selon l'extension du fichier."""
        extension = os.path.splitext(chemin_fichier)[1].lower()  # ".txt"
        # Type par défaut : octets bruts (le navigateur propose de télécharger).
        return self.TYPES_MIME.get(extension, "application/octet-stream")

    def _envoyer_fichier(self, connexion, fichier):
        """Envoie une réponse 200 puis le contenu du fichier."""
        taille = os.path.getsize(fichier)

        # 1) La ligne de statut + les en-têtes (le corps est vide ici)
        entetes = {
            "Content-Type": self._type_mime(fichier),
            "Content-Length": str(taille),
            "Connection": "close",
        }
        connexion.envoyer(ReponseHTTP(200, entetes).vers_octets())

        # 2) Le contenu du fichier, bloc par bloc.
        # On ne charge pas tout le fichier en mémoire : utile pour les gros fichiers.
        with open(fichier, "rb") as f:
            while True:
                bloc = f.read(ConnexionHTTP.TAILLE_BLOC)
                if not bloc:   # b"" = fin du fichier
                    break
                connexion.envoyer(bloc)

    def _envoyer_erreur(self, connexion, code):
        """Envoie une réponse d'erreur (400, 404, 405...)."""
        try:
            connexion.envoyer(ReponseHTTP.erreur(code).vers_octets())
        except OSError:
            pass  # le client est déjà parti


# ----------------------------------------------------------------------
# Programme principal : exécuté seulement si on lance "python3 serveur.py"
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # Valeurs par défaut, remplaçables par les arguments de la ligne de commande.
    port = 8000
    dossier = "partage"
    if len(sys.argv) >= 2:
        port = int(sys.argv[1])
    if len(sys.argv) >= 3:
        dossier = sys.argv[2]

    serveur = ServeurHTTP(port, dossier)
    serveur.demarrer()
