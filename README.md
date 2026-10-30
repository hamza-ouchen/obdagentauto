# AutoDiag AI

Diagnostic automobile pédagogique avec **LangGraph**, **OpenAI via OpenRouter**, **SQLite / OBDb**, interface futuriste sombre et monitoring des agents. Un seul serveur Python, un seul conteneur, un service **Render Free**.

## Lancer

Les dépendances et la clé fournie sont déjà configurées dans cet espace. Depuis ce dossier :

```powershell
python run.py
```

Ouvrir **http://127.0.0.1:8765**. Aucun fichier batch ni activation manuelle de l’environnement n’est nécessaire.

Pour une nouvelle machine avec Python 3.12 :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Copy-Item .env.example .env
python run.py
```

Renseigner `OPENROUTER_API_KEY` dans `.env`. La clé reste côté serveur et n’est ni suivie par Git ni copiée dans Docker. Sans clé, les fiches locales permettent le même parcours en mode démo.

Configuration : `LLM_PROVIDER=openrouter`, `LLM_MODEL=openai/gpt-4o-mini`. Le modèle et les délais du fournisseur sont contrôlés côté serveur. Les tarifs versionnés utilisés pour les estimations de coût figurent dans `app/seed/model-pricing.json`.

## Parcours à essayer

1. Diagnostic IA → P0301 → Toyota Corolla Hybrid → 2020 → Lancer le diagnostic.
2. Observer interprétation, recherche et estimation : **180 DH + 1,5 h × 200 DH = 480 DH**.
3. LangGraph est suspendu. Accepter le devis pour obtenir les créneaux.
4. Choisir un créneau, cocher la confirmation puis confirmer. Ce sont deux validations distinctes.
5. Ouvrir Rendez-vous et télécharger le calendrier `.ics`.
6. Dans Centre des agents, sélectionner le dossier : durées, tokens, coût estimé, événements et Correlation ID.
7. Refuser un devis pour montrer la branche sans agent rendez-vous.
8. Essayer P0999 : branche code non couvert, sans prix inventé.
9. Centre des agents → Simuler un incident : repli local, avertissement et incidents mitigés avec runbook.

Codes disponibles : P0300, P0301, P0302, P0101, P0115, P0128, P0171, P0420, P0442, P0455.

## Architecture réalisée

```text
Navigateur : 6 vues HTML/CSS/JS + Chart.js local
              │ HTTP, même domaine
          FastAPI / LangGraph
              │
 START → interprétation → code connu ? → recherche → estimation
                │ non                              │
                END                        validation du devis
                                            │ refus : END
                                            │ accord
                                      agent rendez-vous
                                            │
                                    validation du créneau
                                            │
                              réservation SQLite → END

 Monitoring transversal : Correlation ID, durées, erreurs, usage, coûts
```

- **Interprétation et recherche** : deux appels linguistiques au modèle OpenAI via OpenRouter, fondés sur les fiches ; repli local en cas d’échec.
- **Estimation** : calcul Python déterministe, aucun prix généré par le modèle.
- **Rendez-vous** : disponibilités et écriture SQLite après confirmation humaine. Unicité du créneau et réservation idempotente par dossier.
- **Monitoring** : événements JSON, règles d’incident, mesures et agrégats. Aucun appel LLM supplémentaire.
- **Deux `interrupt()`**, checkpoints SQLite et reprise du même thread. Aucun rappel des modèles pendant une reprise humaine.
- **Tâche locale FastAPI** pour l’analyse initiale ; l’interface lit l’avancement par requêtes courtes. Les reprises sans LLM sont rapides et synchrones.

Documentation interactive de l’API : **/docs**. Architecture détaillée : [dossier de conception](docs/ARCHITECTURE_ET_PARCOURS.md), [version visuelle](docs/ARCHITECTURE_ET_PARCOURS.html). Les ajustements d’implémentation par rapport au dossier initial sont précisés dans celui-ci.

## Interface et données

Six vues : Tableau de bord, Diagnostic IA, Centre des agents, Historique, Rendez-vous, Projet & validation.

Le thème sombre comprend illustration holographique, cartes par agent, graphe animé, jauges et graphiques. Les métriques de supervision proviennent des exécutions. Le mode Présentation fictive est séparé et ne permet pas d’exporter de fausses traces.

Les jauges automobiles affichent des **valeurs simulées**, jamais des mesures d’une voiture. Les fichiers OBDb définissent les signaux ; ils ne fournissent ni télémétrie réelle ni tarifs de réparation. Les JSON de deux véhicules sont inclus à des commits précis avec crédits et provenance.

Les fiches, causes, prix et atelier sont fictifs. Le véhicule n’adapte pas le prix à une référence constructeur. Aucune connexion matérielle, aucun paiement et aucun message à un atelier réel.

## Vérification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

Les tests utilisent une base temporaire et des appels fournisseur simulés : aucun coût API pendant la suite automatique. Ils couvrent les branches, les deux pauses, les refus, les conflits simultanés, l’idempotence, la reprise SQLite, les coûts, le monitoring et les sources OBDb.

Un test réel du modèle et des vérifications Chrome sont consignés séparément dans [le rapport de livraison](docs/VALIDATION.md). Les résultats locaux ne constituent pas une exécution GitHub Actions ou un déploiement cloud.

## Docker

```powershell
docker build -t autodiag-ai .
docker run --rm -p 127.0.0.1:8765:10000 --env-file .env -e PORT=10000 autodiag-ai
```

Sans clé, retirer `--env-file .env` pour tester le mode démo.

## Déployer sur Render Free

Le projet inclut `.github/workflows/ci.yml`, `Dockerfile`, `.dockerignore`, `render.yaml` et les dépendances verrouillées.

1. Créer un dépôt GitHub, puis y pousser les sources. Ne pas inclure `.env`, `.qa`, `.venv` ou `runtime`.
2. Ouvrir GitHub Actions et vérifier le job AutoDiag validation : tests et démarrage Docker.
3. Dans Render, créer un Blueprint depuis ce dépôt, ou un Web Service Docker au plan **Free**.
4. Renseigner `OPENROUTER_API_KEY` dans les variables d’environnement Render. `LLM_PROVIDER=openrouter`, `LLM_MODEL=openai/gpt-4o-mini` sont déjà déclarés.
5. Facultatif : `GITHUB_REPOSITORY_URL` avec l’URL du dépôt ; elle permet d’ouvrir les preuves CI depuis l’interface.
6. Vérifier le réglage « After CI Checks Pass ». Le job de tests doit réellement s’exécuter, sans être ignoré.
7. Ouvrir l’URL publique et `/api/health`, puis répéter P0301 jusqu’à la réservation.

Le conteneur écoute sur `0.0.0.0` et le `PORT` fourni par Render. Le frontend utilise des routes relatives, sans localhost codé en dur.

**Render Free** peut s’endormir après 15 minutes sans trafic ; le réveil prend environ une minute. Les fichiers locaux sont éphémères. Les données de diagnostic, réservations et traces peuvent disparaître au redémarrage, redéploiement ou endormissement. Les fiches initiales sont automatiquement recréées. Cette limite est acceptée pour le TP ; exporter les preuves avant la soutenance. [Documentation Render](https://render.com/docs/free)

## Livrables et preuves

- [Cinq Agent Cards](docs/agent-cards.json).
- [Runbook RB-LLM-01](docs/RUNBOOK.md).
- [Scénario de vidéo](docs/DEMO_VIDEO.md).
- [Rapport de validation et limites restantes](docs/VALIDATION.md).
- Rapport JSON téléchargeable par diagnostic : State, métriques, événements et incidents.
- [Illustration, prompt de génération et licences](docs/ASSETS.md).

La connexion aux comptes GitHub/Render est nécessaire pour publier en leur nom. Une clé OpenRouter ne donne pas accès à ces plateformes. Tant qu’aucune URL publique et exécution GitHub Actions ne sont vérifiées, ces deux critères restent à finaliser.
