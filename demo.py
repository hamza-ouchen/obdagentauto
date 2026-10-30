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
            if 'estimate' not in run:
                return
            print('\nEstimation :',run['estimate']['total'],'DH')
            accepted=input('Accepter le devis ? [o/N] : ').lower()=='o'
            engine.claim(run_id)
            engine.execute(run_id,{'accepted':accepted})
            run=store.get(run_id)
            if run['status']=='awaiting_booking_approval':
                for index,slot in enumerate(run['slots'][:6],1):
                    print(index,slot)
                choice=input('Confirmer un créneau : numéro, ou Entrée pour ne pas réserver : ')
                selected=int(choice)-1 if choice.isdigit() else -1
                engine.claim(run_id)
                engine.execute(run_id,{'confirmed':0<=selected<6,'slot':run['slots'][selected] if 0<=selected<6 else None})
            run=store.get(run_id)
            print('\nRésultat :',run['status'],run.get('appointment'))
        finally:
            engine.close()
            store.close()


if __name__=='__main__':
    main()
