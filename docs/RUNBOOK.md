# RB-LLM-01 — OpenRouter / OpenAI indisponible

Version 2.0.0 — 30 octobre 2026. Responsable : agent de monitoring, rôle technique Python.

Déclencheurs : délai dépassé, erreur réseau, refus fournisseur, réponse vide ou invalide.

1. Détecter l’erreur. Journaliser la catégorie, l’agent, l’heure et le Correlation ID, sans clé API.
2. Vérifier que la fiche SQLite du code existe.
3. Utiliser cette fiche comme sortie de secours ; ne pas inventer une panne ou un coût.
4. Marquer le dossier degraded=true et afficher l’avertissement de secours.
5. Marquer l’incident mitigated et conserver la liste des actions.
6. Vérifier que le devis est calculé et que LangGraph attend toujours l’accord du client.
7. Exporter le rapport JSON : il contient State, décisions, événements, métriques et incidents.
8. Pour une vraie panne, vérifier la configuration et le fournisseur, puis effectuer un nouvel essai. Une mitigation n’est pas une preuve de rétablissement.

## Démonstration reproductible

Centre des agents → Simuler un incident. Un dossier P0301 est créé avec scenario=openai_unavailable. Aucun appel fournisseur n’est effectué pour ce scénario et aucune configuration globale n’est modifiée.

Attendu : une première erreur fournisseur simulée, puis le questionnaire en pause. Répondre « à froid », « bougies anciennes », « aucun lien avec un plein » pour poursuivre : seconde erreur simulée, repli local, incidents associés à RB-LLM-01, statut awaiting_quote_approval, budget 480 DH et aucune réservation. Sans réponses, aucun budget n’est calculé.

Centre des agents → filtre Scénarios d’incident → sélectionner le dossier → exporter JSON. Le fichier est le compte rendu effectif, avec les étapes appliquées et le même Correlation ID.

## Critère de succès

Le diagnostic reste utilisable en mode dégradé, l’interface l’indique et aucune validation humaine n’est contournée. Les erreurs de base de données ou d’enregistrement de réservation ne sont pas présentées comme une réussite.
