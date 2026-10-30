"""Questionnaires et classement pédagogique des hypothèses.

Les points servent à expliquer le tri des fiches du TP, jamais à afficher une
probabilité médicale/mécanique ou à confirmer une pièce défectueuse.
"""


def question(qid, text, options):
    return {'id': qid, 'text': text, 'options': [
        {'value': value, 'label': label, 'weights': weights}
        for value, label, weights in options
    ] + [{'value': 'unknown', 'label': 'Je ne sais pas / je ne l’ai pas observé', 'weights': [0, 0, 0]}]}


def questionnaire(code):
    if code in ('P0300', 'P0301', 'P0302'):
        return [
            question('conditions', 'Quand remarquez-vous surtout les vibrations ou les ratés ?', [
                ('cold', 'Au démarrage à froid', [2, 0, 1]),
                ('acceleration', 'Quand j’accélère ou que le moteur force', [0, 3, 1]),
                ('all', 'À froid comme à chaud, de manière continue', [1, 1, 1]),
            ]),
            question('maintenance', 'Que savez-vous du dernier remplacement des bougies ?', [
                ('overdue', 'Il remonte à longtemps / l’entretien est en retard', [3, 0, 0]),
                ('recent', 'Les bougies ont été remplacées récemment', [-2, 2, 0]),
            ]),
            question('fuel', 'Avez-vous remarqué un lien avec le carburant ou le démarrage ?', [
                ('after_refuel', 'Le problème est apparu juste après un plein', [0, 0, 3]),
                ('hard_start', 'Le démarrage est difficile, même moteur chaud', [0, 0, 2]),
                ('none', 'Aucun lien particulier avec un plein ou le démarrage', [1, 1, 0]),
            ]),
        ]
    if code == 'P0420':
        return [
            question('conditions', 'Dans quelles conditions le voyant revient-il ?', [
                ('warm', 'Il revient régulièrement après un trajet moteur chaud', [3, 0, 0]),
                ('intermittent', 'Il apparaît et disparaît sans changement évident de conduite', [0, 2, 0]),
            ]),
            question('exhaust_noise', 'Avez-vous remarqué un nouveau bruit d’échappement ?', [
                ('yes', 'Oui, un souffle ou un bruit inhabituel', [0, 0, 4]),
                ('no', 'Non, le bruit me semble habituel', [1, 1, 0]),
            ]),
            question('consumption', 'Votre consommation a-t-elle changé ?', [
                ('increased', 'Oui, elle a augmenté', [0, 2, 0]),
                ('normal', 'Non, elle me semble habituelle', [1, 0, 0]),
            ]),
        ]
    if code in ('P0171', 'P0101'):
        # P0101 place le débitmètre en premier dans le catalogue existant.
        reorder = lambda weights: [weights[1], weights[0], weights[2]] if code == 'P0101' else weights
        return [
            question('intake_noise', 'Entendez-vous un sifflement inhabituel près du moteur ?', [
                ('yes', 'Oui, notamment au ralenti', reorder([3, 0, 0])),
                ('no', 'Non, je n’ai pas remarqué de sifflement', reorder([0, 1, 1])),
            ]),
            question('conditions', 'Quand le moteur se comporte-t-il le moins bien ?', [
                ('idle', 'Au ralenti, surtout à froid', reorder([2, 0, 0])),
                ('acceleration', 'À l’accélération, avec une perte de puissance', reorder([0, 2, 1])),
            ]),
            question('recent_work', 'Y a-t-il eu un événement récent avant l’apparition du défaut ?', [
                ('intake_work', 'Une intervention sur le filtre à air ou l’admission', reorder([2, 1, 0])),
                ('fuel_issue', 'Des difficultés d’alimentation en carburant déjà signalées', reorder([0, 0, 3])),
                ('none', 'Aucun événement particulier à ma connaissance', reorder([0, 0, 0])),
            ]),
        ]
    if code in ('P0115', 'P0128'):
        return [
            question('temperature', 'Que montre l’indicateur de température pendant vos trajets ?', [
                ('low', 'Le moteur met longtemps à chauffer / reste anormalement froid', [4 if code == 'P0128' else 1, 0, 0]),
                ('erratic', 'L’indication saute ou paraît incohérente', [3 if code == 'P0115' else 0, 2, 1]),
            ]),
            question('conditions', 'Le phénomène est-il répétitif ?', [
                ('every_trip', 'Oui, à presque chaque trajet', [2, 0, 0]),
                ('intermittent', 'Non, il est intermittent', [0, 2, 1]),
            ]),
            question('recent_work', 'Le problème a-t-il commencé après une intervention ?', [
                ('electrical', 'Oui, après une intervention électrique', [0, 1, 3]),
                ('none', 'Non, aucune intervention récente connue', [1, 0, 0]),
            ]),
        ]
    return [
        question('refuel', 'Quand le voyant est-il apparu par rapport au dernier plein ?', [
            ('after', 'Juste après un plein', [3, 0, 1]),
            ('unrelated', 'Sans lien apparent avec un plein', [0, 1, 1]),
        ]),
        question('cap', 'Avez-vous déjà remarqué un problème avec le bouchon du réservoir ?', [
            ('loose', 'Il était mal fermé ou son joint semblait abîmé', [4, 0, 0]),
            ('normal', 'Il était correctement fermé, sans anomalie visible', [-1, 1, 1]),
        ]),
        question('start', 'Comment se passe le démarrage après un plein ?', [
            ('hard', 'Il est plus difficile que d’habitude', [0, 0, 3]),
            ('normal', 'Il est habituel, sans difficulté particulière', [1, 1, 0]),
        ]),
    ]


def public_questions(code):
    return [{**q, 'options': [{'value': o['value'], 'label': o['label']} for o in q['options']]} for q in questionnaire(code)]


def validate_answers(code, answers):
    questions = questionnaire(code)
    if set(answers) != {q['id'] for q in questions}:
        raise ValueError('Répondez à toutes les questions ; « Je ne sais pas » est une réponse acceptée.')
    if any(answers[q['id']] not in {o['value'] for o in q['options']} for q in questions):
        raise ValueError('Une réponse ne correspond pas aux choix proposés.')


def assess(code, answers, causes):
    validate_answers(code, answers)
    scores = [0] * len(causes)
    evidence = [[] for _ in causes]
    answered = []
    for q in questionnaire(code):
        option = next(o for o in q['options'] if o['value'] == answers[q['id']])
        answered.append({'question': q['text'], 'answer': option['label'], 'unknown': option['value'] == 'unknown'})
        for index, weight in enumerate(option['weights']):
            if index < len(causes):
                scores[index] += weight
                if weight > 0:
                    evidence[index].append(option['label'])
    ranking = sorted(range(len(causes)), key=lambda i: (-scores[i], i))
    top, second = ranking[:2]
    informative = sum(not a['unknown'] for a in answered)
    supported = informative >= 2 and scores[top] >= 3 and scores[top] - scores[second] >= 2 and len(evidence[top]) >= 2
    selected = top if supported else None
    reason = (f"Vos réponses orientent davantage vers « {causes[top]['name']} » : " + ' ; '.join(evidence[top]) + '. Cette hypothèse reste à confirmer par des contrôles en atelier.') if supported else 'Les réponses ne permettent pas de départager suffisamment les causes. Aucun problème unique n’est choisi ; plusieurs scénarios de coût sont présentés.'
    return {'status': 'supported' if supported else 'uncertain', 'selected_index': selected,
            'reason': reason, 'answers': answered, 'informative_answers': informative,
            'ranked_causes': [{'index': i, 'name': causes[i]['name'], 'score': scores[i], 'evidence': evidence[i]} for i in ranking],
            'method': 'Règles pédagogiques explicites + synthèse IA si disponible',
            'caveat': 'Les points de classement ne sont pas des probabilités. Un code et des symptômes ne confirment pas une pièce défectueuse.'}
