# Oracle local pour AuditAI

Cette base reproduit le contrat utilisé par le backend :
`SMART2DSECU.UNIFIED_AUDIT_DATA`. Elle contient 5 003 événements simulés sur 90 jours et un
catalogue sémantique français. `AUDITAI_READER` possède uniquement le droit `SELECT`.

## Démarrage dans Oracle Linux WSL

1. Copier `.env.example` vers `.env` et remplacer les trois mots de passe.
2. Depuis ce dossier : `docker compose pull`, puis `docker compose up -d`.
3. Attendre que les journaux indiquent que la base est prête.

Connexion backend locale :

```text
host     = localhost
port     = 1521
service  = FREEPDB1
user     = AUDITAI_READER
table    = SMART2DSECU.UNIFIED_AUDIT_DATA
```

La base fonctionne sans Internet après le téléchargement initial de l'image. Les requêtes de
l'application doivent rester en lecture seule. Les actions `DELETE`, `GRANT`, `TRUNCATE`, etc.
sont uniquement des valeurs de la colonne `ACTION_NAME`.

