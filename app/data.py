"""Fiches pédagogiques fictives importées dans SQLite à l’initialisation."""

DEMO_CODES = {
    "P0301": {
        "title": "Ratés d’allumage · cylindre 1",
        "description": "Le cylindre n° 1 ne brûle pas correctement le mélange air-carburant. Cela peut provoquer des vibrations, une perte de puissance et une consommation plus élevée.",
        "system": "Allumage", "severity": "À contrôler", "hours": 1.5,
        "causes": [
            {"name": "Bougie d’allumage usée", "detail": "Contrôler l’état et l’écartement de la bougie du cylindre 1.", "likelihood": "Élevée", "parts": 180},
            {"name": "Bobine d’allumage défectueuse", "detail": "Permuter la bobine avec un autre cylindre et vérifier si le défaut se déplace.", "likelihood": "Moyenne", "parts": 650},
            {"name": "Injecteur encrassé", "detail": "Vérifier le débit de l’injecteur et son alimentation électrique.", "likelihood": "Faible", "parts": 950},
        ],
    },
    "P0420": {
        "title": "Efficacité du catalyseur insuffisante",
        "description": "Le calculateur détecte une efficacité trop faible du système catalytique sur la rangée 1. Un contrôle des sondes et de l’échappement permettra d’identifier la cause.",
        "system": "Échappement", "severity": "À contrôler", "hours": 2.0,
        "causes": [
            {"name": "Catalyseur usé", "detail": "Mesurer l’efficacité du catalyseur avant tout remplacement.", "likelihood": "Élevée", "parts": 3200},
            {"name": "Sonde lambda vieillissante", "detail": "Comparer les signaux des sondes en amont et en aval.", "likelihood": "Moyenne", "parts": 750},
            {"name": "Fuite à l’échappement", "detail": "Contrôler les raccords et les joints de la ligne.", "likelihood": "Faible", "parts": 250},
        ],
    },
    "P0171": {
        "title": "Mélange air-carburant trop pauvre",
        "description": "Le moteur reçoit trop d’air ou pas assez de carburant sur la rangée 1. Il compense en augmentant l’injection ; une prise d’air ou un capteur peut être en cause.",
        "system": "Admission", "severity": "À contrôler", "hours": 1.0,
        "causes": [
            {"name": "Prise d’air à l’admission", "detail": "Vérifier l’étanchéité des durites et des joints d’admission.", "likelihood": "Élevée", "parts": 250},
            {"name": "Débitmètre encrassé", "detail": "Contrôler les mesures du débitmètre d’air.", "likelihood": "Moyenne", "parts": 850},
            {"name": "Pression de carburant faible", "detail": "Mesurer la pression de la pompe à carburant.", "likelihood": "Faible", "parts": 1200},
        ],
    },
    "P0115": {
        "title": "Circuit du capteur de température moteur",
        "description": "Le signal de température du liquide de refroidissement est incohérent. Le capteur ou son câblage doit être contrôlé.",
        "system": "Refroidissement", "severity": "À contrôler", "hours": 0.75,
        "causes": [
            {"name": "Capteur de température défectueux", "detail": "Comparer la température lue à la température réelle du moteur.", "likelihood": "Élevée", "parts": 220},
            {"name": "Connecteur oxydé", "detail": "Inspecter et nettoyer les contacts électriques.", "likelihood": "Moyenne", "parts": 80},
            {"name": "Faisceau endommagé", "detail": "Contrôler la continuité du circuit.", "likelihood": "Faible", "parts": 350},
        ],
    },
    "P0455": {
        "title": "Fuite importante du système EVAP",
        "description": "Le système de récupération des vapeurs de carburant présente une fuite importante. Le bouchon de réservoir est un premier point de contrôle.",
        "system": "Antipollution", "severity": "À contrôler", "hours": 0.5,
        "causes": [
            {"name": "Bouchon de réservoir non étanche", "detail": "Vérifier le serrage et l’état du joint du bouchon.", "likelihood": "Élevée", "parts": 120},
            {"name": "Durite EVAP fissurée", "detail": "Inspecter les conduites de récupération des vapeurs.", "likelihood": "Moyenne", "parts": 200},
            {"name": "Électrovanne de purge bloquée", "detail": "Tester l’ouverture et la fermeture de l’électrovanne.", "likelihood": "Faible", "parts": 450},
        ],
    },
}

from copy import deepcopy

for _code, _base, _title, _description in [
    ("P0300", "P0301", "Ratés d’allumage multiples ou aléatoires", "Le calculateur détecte des ratés sur plusieurs cylindres ou de façon aléatoire. Contrôler l’allumage et l’alimentation."),
    ("P0302", "P0301", "Ratés d’allumage · cylindre 2", "Le calculateur détecte des ratés de combustion sur le cylindre n° 2. Les causes sont des hypothèses à vérifier."),
    ("P0101", "P0171", "Débitmètre d’air · signal incohérent", "Le débit d’air mesuré ne correspond pas à la plage attendue. Inspecter l’admission et le débitmètre."),
    ("P0128", "P0115", "Température moteur trop basse", "Le moteur n’atteint pas la température attendue assez rapidement. Vérifier le thermostat et le capteur."),
    ("P0442", "P0455", "Petite fuite du système EVAP", "Le système de récupération des vapeurs de carburant présente une petite fuite. Contrôler les joints et conduites."),
]:
    DEMO_CODES[_code] = deepcopy(DEMO_CODES[_base])
    DEMO_CODES[_code].update(title=_title, description=_description)
for _code in ("P0300", "P0302"):
    for _cause in DEMO_CODES[_code]["causes"]:
        _cause["detail"] = _cause["detail"].replace("cylindre 1", "cylindre 2" if _code == "P0302" else "cylindres concernés")
DEMO_CODES["P0300"]["causes"][0]["name"] = "Bougies d’allumage usées"
DEMO_CODES["P0101"]["causes"].insert(0, DEMO_CODES["P0101"]["causes"].pop(1))
DEMO_CODES["P0101"]["causes"][0]["likelihood"] = "Élevée"
DEMO_CODES["P0101"]["causes"][1]["likelihood"] = "Moyenne"
DEMO_CODES["P0128"]["causes"][0].update(name="Thermostat bloqué ouvert", detail="Vérifier la montée en température et le thermostat.", parts=380)
