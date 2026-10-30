# Rapport de vérification — AutoDiag AI 2.1.0

Date : 30 octobre 2026. Les statuts ci-dessous distinguent les vérifications locales des services externes.

## Vérifié localement

- 31 tests Python automatisés : parcours nominal, dix fiches, trois pauses humaines, refus du devis, refus de réservation, code inconnu, créneau invalide, conflits, confirmations simultanées, idempotence, reprise d’un checkpoint SQLite, monitoring, coûts, tokens en cache et provenance OBDb.
- Chrome : parcours complet, accord du devis, sélection sans réservation prématurée, confirmation, téléchargement ICS, recherche dans l’historique, rechargement du dossier, supervision, séparation des données de présentation, incident simulé et cinq Agent Cards.
- Six vues mobiles testées à 390 pixels : pas de débordement horizontal. Aucun événement JavaScript pageerror pendant le parcours.
- Vrais appels au modèle `openai/gpt-4o-mini` via OpenRouter : interprétation et analyse des réponses réussies sans repli, avec usage et coût estimé enregistrés dans les exports. Les réponses différentes ont produit deux hypothèses et deux budgets différents ; les réponses inconnues ont conservé une fourchette.
- Image Docker construite et conteneur démarré sous Linux ; `/api/health` répond 200 avec version 2.1.0 ; P0301 atteint la pause du devis avec total 480 DH.
- Dépendances verrouillées, clé exclue de Git et de l’image Docker, bibliothèque Chart.js et visuel fournis localement.

## Preuves incluses

- `docs/preuves/diagnostic-P0301.json` : exécution réelle, décisions, réservation et trace corrélée.
- `docs/preuves/incident-simule.json` : incident contrôlé, repli et actions du runbook. L’origine simulée est explicite.
- `docs/preuves/verification-navigateur.json` : résultat des contrôles Chrome.
- `docs/preuves/verification-interface-finale.json` : formulaire, champs immuables, filtres et décodage vidéo vérifiés ; vidéo de 69,92 secondes en 1512 × 980.
- `docs/preuves/verification-docker.json` : parcours complet contrôlé dans le conteneur final, jusqu’à la réservation.
- `docs/preuves/tableau-de-bord.png` et `centre-agents.png` : captures de l’interface.
- `docs/DEMONSTRATION.webm` : vidéo locale avec explications à l’écran, sans audio.
- `docs/agent-cards.json` et `docs/RUNBOOK.md` : gouvernance et procédure d’incident.

## Préparé, mais pas déclaré validé à distance

- GitHub Actions : workflow fourni et suite exécutée localement ; aucune exécution distante ne peut être annoncée réussie tant que le dépôt n’a pas été publié et le job vérifié.
- Render Free : Dockerfile, Blueprint, variables et healthcheck fournis. L’URL publique doit encore être obtenue et son parcours vérifié.
- Les connexions indiquées par l’utilisateur ne sont pas exposées aux outils de cette session. Aucun jeton GitHub/Render local utilisable n’a été trouvé. La clé OpenRouter n’autorise pas ces publications.

Le projet ne doit donc pas être présenté comme satisfaisant déjà la totalité des critères du professeur : les preuves GitHub Actions et Render restent à produire.

## Limites explicites

Les fiches, tarifs et réservations sont fictifs. La télémétrie est simulée. SQLite est éphémère sur Render Free. Il n’y a pas de comptes clients, de paiement, d’annulation après confirmation ni de connexion OBD matérielle. Une erreur fournisseur entraîne un repli signalé ; une erreur d’écriture n’est jamais annoncée comme une réservation réussie.

Le monitoring calcule un coût estimé à partir de l’usage disponible et des tarifs versionnés. Un usage absent est signalé ; la réussite technique d’un parcours n’est pas une mesure de précision du diagnostic.

## Ajouts 2.1

- Aucun devis avant le questionnaire. Trois questions adaptées au code, avec Je ne sais pas.
- Hypothèse orientée par les observations ou absence de choix unique en cas d’incertitude.
- Prénom, nom, téléphone et email obligatoires avant une nouvelle réservation.
- Coordonnées conservées dans le dossier, exclues des journaux de monitoring et des listes globales de contact.
- Captures questionnaire.png, coordonnees-client.png et estimation-incertaine.png incluses.
- Les règles de classement sont pédagogiques, sans probabilité de panne validée.
