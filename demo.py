"""Démonstration console autonome : python demo.py (sans serveur web)."""
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from app.graph import Engine
from app.storage import Store, utcnow
from uuid import uuid4


def main():
    load_dotenv()
    with tempfile.TemporaryDirectory() as directory:
        store=Store(Path(directory)/'demo.sqlite')
        engine=Engine(store)
        try:
            code=input('Code OBD-II [P0301] : ').strip().upper() or 'P0301'
            run_id=uuid4().hex
            store.create({'id':run_id,'correlation_id':run_id,'code':code,'vehicle':'Non précisé','status':'queued','created_at':utcnow(),'providers':{},'appointment':None})
            engine.claim(run_id)
            engine.execute(run_id)
            run=store.get(run_id)
            print('\nCorrelation ID :',run_id,'\nStatut :',run['status'])
            print(run.get('interpretation',''))
            if run['status']=='awaiting_symptom_answers':
                answers={}
                for question in run['questions']:
                    print('\n'+question['text'])
                    for index,option in enumerate(question['options'],1):
                        print(index,option['label'])
                    while True:
                        choice=input('Votre choix (numéro, Entrée = Je ne sais pas) : ').strip()
                        if not choice:
                            answers[question['id']]='unknown'
                            break
                        if choice.isdigit() and 1<=int(choice)<=len(question['options']):
                            answers[question['id']]=question['options'][int(choice)-1]['value']
                            break
                engine.claim(run_id)
                engine.execute(run_id,{'answers':answers})
                run=store.get(run_id)
            if 'estimate' not in run:
                return
            estimate=run['estimate']
            print('\nHypothèses :',run['assessment']['reason'])
            print('\nEstimation :',str(estimate['total']) if estimate['total'] is not None else f"{estimate['min_total']} à {estimate['max_total']}",'DH')
            accepted=input('Accepter le devis ? [o/N] : ').lower()=='o'
            engine.claim(run_id)
            engine.execute(run_id,{'accepted':accepted})
            run=store.get(run_id)
            if run['status']=='awaiting_booking_approval':
                for index,slot in enumerate(run['slots'][:6],1):
                    print(index,slot)
                choice=input('Confirmer un créneau : numéro, ou Entrée pour ne pas réserver : ')
                selected=int(choice)-1 if choice.isdigit() else -1
                customer=None
                if 0<=selected<6:
                    from app.main import CustomerInput
                    while customer is None:
                        try:
                            customer=CustomerInput(first_name=input('Prénom : '),last_name=input('Nom : '),phone=input('Téléphone : '),email=input('Email : ')).model_dump()
                        except ValueError:
                            print('Coordonnées invalides. Renseignez les quatre champs.')
                engine.claim(run_id)
                engine.execute(run_id,{'confirmed':0<=selected<6,'slot':run['slots'][selected] if 0<=selected<6 else None,'customer':customer})
            run=store.get(run_id)
            print('\nRésultat :',run['status'],run.get('appointment'))
        finally:
            engine.close()
            store.close()


if __name__=='__main__':
    main()
