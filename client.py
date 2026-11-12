"""
client.py
=========
Client HTTP minimal : il télécharge un fichier depuis un serveur HTTP
standard (httpd d'Apache dans Docker) ou depuis notre serveur (serveur.py).

Utilisation :
    python3 client.py hote port chemin [destination]
Exemples :
    python3 client.py localhost 8080 /test.txt
    python3 client.py localhost 8000 /exemple.txt copie.txt

Par défaut, le fichier est enregistré dans le dossier "telechargements/".

Diagramme correspondant : D2 (télécharger un fichier).
"""

import os
import socket
import sys

from http_commun import ConnexionHTTP, ErreurHTTP, ReponseHTTP, RequeteHTTP


class ErreurTelechargement(Exception):
    """Le téléchargement a échoué (serveur injoignable, erreur 404...)."""

    def __init__(self, raison):
        super().__init__(raison)
        self.raison = raison


class ClientHTTP:
    """Client qui télécharge un fichier avec une requête GET."""

    def __init__(self, hote, port, delai=10.0):
        self.hote = hote    # ex : "localhost"
        self.port = port    # ex : 8080
        self.delai = delai  # secondes d'attente max avant d'abandonner

    # ------------------------------------------------------------------
    # Méthode publique
    # ------------------------------------------------------------------

    def telecharger(self, chemin, destination):
        """Télécharge `chemin` (ex : "/test.txt") dans le fichier `destination`.

        Lève ErreurTelechargement en cas de problème.
        """
        # 1) Connexion TCP au serveur
        connexion = self._ouvrir_connexion()
        try:
            # 2) Envoi de la requête GET
            self._envoyer_requete(connexion, chemin)

            # 3) Lecture de la ligne de statut et des en-têtes
            reponse = self._recevoir_reponse(connexion)
            if reponse.code != 200:
                raise ErreurTelechargement(
                    "code d'erreur reçu : " + str(reponse.code) + " " + reponse.raison)

            # 4) Combien d'octets attendre ?
            taille = reponse.taille_corps()
            if taille < 0:
                raise ErreurTelechargement("en-tête Content-Length absent")

            # 5) Lecture du corps et écriture sur le disque
            recus = self._ecrire_fichier(connexion, taille, destination)
            if recus < taille:
                raise ErreurTelechargement(
                    "connexion interrompue (" + str(recus) + "/" + str(taille) + " octets)")

            print("Téléchargement terminé :", destination, "(" + str(recus) + " octets)")

        except ErreurHTTP:
            # La réponse du serveur ne respecte pas le format HTTP.
            raise ErreurTelechargement("réponse HTTP invalide")
        except socket.timeout:
            raise ErreurTelechargement("le serveur ne répond plus")
        finally:
            # 6) Dans tous les cas, on ferme la connexion.
            connexion.fermer()

    # ------------------------------------------------------------------
    # Méthodes privées
    # ------------------------------------------------------------------

    def _ouvrir_connexion(self):
        """Ouvre la connexion TCP vers le serveur."""
        try:
            # create_connection() = créer la socket + connect((hote, port))
            sock = socket.create_connection((self.hote, self.port), timeout=self.delai)
        except OSError:
            # ConnectionRefusedError, timeout, nom d'hôte inconnu...
            # sont toutes des sous-classes de OSError.
            raise ErreurTelechargement("serveur injoignable")
        return ConnexionHTTP(sock, (self.hote, self.port))

    def _envoyer_requete(self, connexion, chemin):
        """Construit et envoie la requête GET."""
        entetes = {
            "Host": self.hote + ":" + str(self.port),  # obligatoire en HTTP/1.1
            "User-Agent": "ClientHTTP-Projet/1.0",      # qui fait la requête
            "Connection": "close",  # le serveur fermera après la réponse
        }
        requete = RequeteHTTP("GET", chemin, entetes)
        connexion.envoyer(requete.vers_octets())

    def _recevoir_reponse(self, connexion):
        """Lit les en-têtes de la réponse et les transforme en ReponseHTTP."""
        octets = connexion.lire_entetes()
        return ReponseHTTP.depuis_octets(octets)

    def _ecrire_fichier(self, connexion, taille, destination):
        """Écrit le corps de la réponse dans `destination`.

        Renvoie le nombre d'octets reçus.
        """
        # "wb" = écriture en binaire (marche pour texte, images, PDF...)
        with open(destination, "wb") as fichier:
            return connexion.lire_corps(taille, fichier)


# ----------------------------------------------------------------------
# Programme principal
# ----------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Utilisation : python3 client.py hote port chemin [destination]")
        print("Exemple     : python3 client.py localhost 8080 /test.txt")
        sys.exit(1)

    hote = sys.argv[1]
    port = int(sys.argv[2])
    chemin = sys.argv[3]

    if len(sys.argv) >= 5:
        destination = sys.argv[4]
    else:
        # Par défaut : telechargements/<nom du fichier>
        os.makedirs("telechargements", exist_ok=True)
        nom = os.path.basename(chemin) or "index.html"
        destination = os.path.join("telechargements", nom)

    client = ClientHTTP(hote, port)
    try:
        client.telecharger(chemin, destination)
    except ErreurTelechargement as e:
        print("Échec du téléchargement :", e.raison)
        sys.exit(1)
