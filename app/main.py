import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from app.graph import AGENTS, Engine
from app.llm import provider_config
from app.storage import Store, utcnow
from app.symptoms import validate_answers

ROOT=Path(__file__).resolve().parent.parent
load_dotenv(ROOT/'.env')
logging.basicConfig(level=logging.INFO,format='%(message)s')
VERSION='2.1.0'
TERMINAL={'booked','price_declined','booking_declined','unknown_code','no_slots','failed'}


class DiagnosticInput(BaseModel):
    code:str=Field(min_length=5,max_length=5,pattern=r'^[PBCU][0-3][0-9A-F]{3}$')
    vehicle_id:Literal['toyota-corolla-hybrid','honda-civic']|None=None
    year:int|None=Field(default=None,ge=1990,le=2030)
    scenario:Literal['openai_unavailable']|None=None

    @field_validator('code',mode='before')
    @classmethod
    def normalize(cls,value):
        return value.strip().upper() if isinstance(value,str) else value


class QuoteInput(BaseModel):
    accepted:bool


class SymptomsInput(BaseModel):
    answers:dict[str,str]=Field(min_length=1,max_length=10)


class CustomerInput(BaseModel):
    first_name:str=Field(min_length=1,max_length=80)
    last_name:str=Field(min_length=1,max_length=80)
    phone:str=Field(min_length=7,max_length=25)
    email:str=Field(max_length=254,pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

    @field_validator('first_name','last_name','phone','email',mode='before')
    @classmethod
    def clean(cls,value):
        return value.strip() if isinstance(value,str) else value

    @field_validator('phone')
    @classmethod
    def validate_phone(cls,value):
        digits=re.sub(r'[^0-9]','',value)
        if not re.fullmatch(r'\+?[0-9 ()\-.]+',value) or not 7<=len(digits)<=15:
            raise ValueError('Numéro de téléphone invalide.')
        return value


class BookingInput(BaseModel):
    confirmed:bool
    slot:str|None=None
    customer:CustomerInput|None=None


def create_app(db_path=None):
    @asynccontextmanager
    async def lifespan(app):
        store=Store(db_path or os.getenv('DATABASE_PATH',str(ROOT/'runtime/autodiag.sqlite')))
        engine=Engine(store)
        app.state.store,app.state.engine=store,engine
        for run in store.runs():
            if run['status'] in ('queued','running'):
                store.merge(run['id'],{'status':'failed','error':'Le serveur a redémarré pendant le calcul. Relancez une analyse.'})
        yield
        engine.close()
        store.close()

    app=FastAPI(title='AutoDiag AI',description='TP LangGraph · OpenRouter · OBDb · monitoring',version=VERSION,lifespan=lifespan)
    app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')

    def get_run(run_id):
        run=app.state.store.get(run_id)
        if not run:
            raise HTTPException(404,'Dossier introuvable ou session expirée. Les données du TP sont temporaires.')
        return run

    def enrich(run,after=0):
        events=app.state.store.events(run['id'],after)
        completed=[e for e in app.state.store.events(run['id']) if e['kind']=='agent.completed']
        return {**run,'events':events,'metrics':{'input_tokens':sum(e.get('input_tokens') or 0 for e in completed),'output_tokens':sum(e.get('output_tokens') or 0 for e in completed),'cost_usd':sum(e.get('cost_usd') or 0 for e in completed),'incomplete_usage':any(e.get('cost_usd') is None for e in completed)}}

    @app.get('/')
    def index():
        return FileResponse(ROOT/'static/index.html',headers={'Cache-Control':'no-cache'})

    @app.get('/api/health')
    def health():
        with app.state.store.lock:
            app.state.store.db.execute('SELECT 1').fetchone()
        return {'status':'ok','version':VERSION}

    @app.get('/api/bootstrap')
    def bootstrap():
        config=provider_config()
        vehicles=app.state.store.vehicles(2020)
        return {'version':VERSION,'provider':config['provider'],'model':config['model'],'configured':bool(config['key']),'codes':app.state.store.codes(),'vehicles':[{**v,'signals':v['signals'][:12]} for v in vehicles],'temporary_data':True}

    @app.get('/api/codes')
    def codes():
        return app.state.store.codes()

    @app.post('/api/diagnostics',status_code=202)
    def diagnose(body:DiagnosticInput,tasks:BackgroundTasks):
        run_id=uuid4().hex
        vehicles=app.state.store.vehicles(body.year,body.vehicle_id) if body.vehicle_id else []
        vehicle=vehicles[0]['name']+(f' {body.year}' if body.year else '') if vehicles else 'Véhicule non précisé'
        state={'id':run_id,'correlation_id':run_id,'code':body.code,'vehicle_id':body.vehicle_id,'vehicle':vehicle,'year':body.year,'scenario':body.scenario,'workflow_version':VERSION,'status':'queued','created_at':utcnow(),'updated_at':utcnow(),'providers':{},'degraded':False,'appointment':None,'processing_ms':0}
        app.state.store.create(state)
        app.state.engine.claim(run_id)
        tasks.add_task(app.state.engine.execute,run_id)
        return {'id':run_id,'status':'queued','status_url':f'/api/diagnostics/{run_id}'}

    @app.get('/api/diagnostics')
    def history():
        results=[]
        for run in app.state.store.runs():
            if run.get('appointment'):
                run['appointment']={k:v for k,v in run['appointment'].items() if k!='customer'}
            results.append(run)
        return results

    @app.get('/api/diagnostics/{run_id}')
    def detail(run_id:str,after_event:int=Query(default=0,ge=0)):
        return enrich(get_run(run_id),after_event)

    @app.post('/api/diagnostics/{run_id}/symptoms',status_code=202)
    def symptom_answers(run_id:str,body:SymptomsInput,tasks:BackgroundTasks):
        engine=app.state.engine
        with engine.guard:
            run=get_run(run_id)
            if run['status']!='awaiting_symptom_answers':
                raise HTTPException(409,'Ce dossier n’attend plus de réponses au questionnaire.')
            try:
                validate_answers(run['code'],body.answers)
            except ValueError as exc:
                raise HTTPException(422,str(exc)) from exc
            if not engine.claim(run_id):
                raise HTTPException(409,'Une analyse de réponses est déjà en cours.')
            app.state.store.merge(run_id,{'status':'running'})
            tasks.add_task(engine.execute,run_id,body.model_dump())
        return {'id':run_id,'status':'running','status_url':f'/api/diagnostics/{run_id}'}

    @app.post('/api/diagnostics/{run_id}/quote-decision')
    def quote_decision(run_id:str,body:QuoteInput):
        engine=app.state.engine
        with engine.guard:
            run=get_run(run_id)
            if run['status']!='awaiting_quote_approval' or not engine.claim(run_id):
                raise HTTPException(409,'Ce devis n’attend plus de décision. Actualisez le dossier.')
            if body.accepted and 'assessment' not in run:
                engine.active.discard(run_id)
                raise HTTPException(409,'Ce dossier précède le questionnaire. Relancez une nouvelle analyse pour préciser les symptômes.')
            app.state.store.merge(run_id,{'status':'running'})
            engine.execute(run_id,body.model_dump())
        return enrich(get_run(run_id))

    @app.get('/api/diagnostics/{run_id}/slots')
    def slots(run_id:str):
        run=get_run(run_id)
        available=set(app.state.store.slots())
        return [slot for slot in run.get('slots',[]) if slot in available]

    @app.post('/api/diagnostics/{run_id}/booking-decision')
    def booking_decision(run_id:str,body:BookingInput):
        engine=app.state.engine
        with engine.guard:
            run=get_run(run_id)
            if run['status']=='booked' and body.confirmed and run['appointment']['slot']==body.slot:
                return enrich(run)
            if run['status']!='awaiting_booking_approval':
                raise HTTPException(409,'Ce dossier n’attend plus de réservation.')
            if body.confirmed:
                if body.customer is None:
                    raise HTTPException(422,'Renseignez le nom, le prénom, le téléphone et l’email du client.')
                if not body.slot or body.slot not in run.get('slots',[]):
                    raise HTTPException(422,'Choisissez un créneau proposé.')
                if body.slot not in app.state.store.slots():
                    raise HTTPException(409,'Ce créneau vient d’être réservé. Choisissez-en un autre.')
            if not engine.claim(run_id):
                raise HTTPException(409,'Une confirmation est déjà en cours.')
            app.state.store.merge(run_id,{'status':'running'})
            engine.execute(run_id,body.model_dump())
        return enrich(get_run(run_id))

    @app.get('/api/diagnostics/{run_id}/events')
    def events(run_id:str,after_event:int=Query(default=0,ge=0)):
        get_run(run_id)
        return app.state.store.events(run_id,after_event)

    @app.get('/api/diagnostics/{run_id}/export')
    def export(run_id:str):
        data=enrich(get_run(run_id))
        data['incidents']=[i for i in app.state.store.incidents() if i['correlation_id']==run_id]
        return Response(json.dumps(data,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="autodiag-{data["code"]}-{run_id[:8]}.json"'})

    @app.get('/api/appointments')
    def appointments():
        return [{**{k:v for k,v in a.items() if k!='customer'},'customer_name':' '.join(a.get('customer',{}).get(k,'') for k in ('first_name','last_name')).strip()} for a in app.state.store.appointments()]

    @app.get('/api/appointments/{appointment_id}/calendar')
    def calendar(appointment_id:str):
        appointment=next((a for a in app.state.store.appointments() if a['id']==appointment_id),None)
        if not appointment:
            raise HTTPException(404,'Réservation introuvable.')
        start=datetime.fromisoformat(appointment['slot'])
        from datetime import timezone
        fmt=lambda d:d.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        text='\r\n'.join(['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//AutoDiag AI//TP//FR','BEGIN:VEVENT',f'UID:{appointment_id}@autodiag.local',f'DTSTAMP:{fmt(datetime.now(timezone.utc))}',f'DTSTART:{fmt(start)}',f'DTEND:{fmt(start+timedelta(hours=1))}',f'SUMMARY:Diagnostic {appointment["code"]} - AutoDiag','LOCATION:Atelier fictif - Casablanca','DESCRIPTION:Reservation pedagogique. Aucun garage reel contacte.','END:VEVENT','END:VCALENDAR',''])
        return Response(text,media_type='text/calendar',headers={'Content-Disposition':f'attachment; filename="autodiag-{appointment_id}.ics"'})

    @app.get('/api/monitoring/incidents')
    def incidents():
        return app.state.store.incidents()

    @app.get('/api/monitoring/summary')
    def summary(origin:Literal['all','app','scenario']='app',agent:str|None=None,code:str|None=None,days:int|None=Query(default=None,ge=1,le=365)):
        runs=[r for r in app.state.store.runs() if origin=='all' or bool(r.get('scenario'))==(origin=='scenario')]
        if days:
            from datetime import timezone
            since=datetime.now(timezone.utc)-timedelta(days=days)
            runs=[r for r in runs if datetime.fromisoformat(r['created_at'])>=since]
        if code:
            runs=[r for r in runs if code.upper() in r['code'] or code.lower() in r['id']]
        ids={r['id'] for r in runs}
        events=[e for e in app.state.store.events() if e['correlation_id'] in ids and (not agent or e['agent']==agent)]
        done=[e for e in events if e['kind']=='agent.completed']
        closed=[r for r in runs if r['status'] in TERMINAL]
        agents=[]
        for name in AGENTS:
            entries=[e for e in done if e['agent']==name]
            agents.append({'id':name,'executions':len(entries),'avg_ms':round(sum(e.get('duration_ms',0) for e in entries)/len(entries)) if entries else 0,'errors':sum(e['agent']==name and e['kind'] in ('provider.error','agent.failed') for e in events),'input_tokens':sum(e.get('input_tokens') or 0 for e in entries),'output_tokens':sum(e.get('output_tokens') or 0 for e in entries),'cost_usd':sum(e.get('cost_usd') or 0 for e in entries)})
        return {'runs':len(runs),'closed':len(closed),'failures':sum(r['status']=='failed' for r in closed),'success_rate':round(100*sum(r['status']!='failed' for r in closed)/len(closed),1) if closed else None,'degraded':sum(bool(r.get('degraded')) for r in runs),'avg_ms':round(sum(r.get('processing_ms',0) for r in runs)/len(runs)) if runs else 0,'input_tokens':sum(e.get('input_tokens') or 0 for e in done),'output_tokens':sum(e.get('output_tokens') or 0 for e in done),'cost_usd':sum(e.get('cost_usd') or 0 for e in done),'incomplete_usage':any(e.get('cost_usd') is None for e in done),'agents':agents,'events':events[-100:],'series':[{'id':r['id'],'code':r['code'],'ms':r.get('processing_ms',0)} for r in reversed(runs[:12])],'incidents':[i for i in app.state.store.incidents() if i['correlation_id'] in ids]}

    @app.get('/api/project')
    def project():
        cards_path=ROOT/'docs/agent-cards.json'
        return {'version':VERSION,'commit':os.getenv('RENDER_GIT_COMMIT','local'),'repository':os.getenv('GITHUB_REPOSITORY_URL',''),'cards':json.loads(cards_path.read_text(encoding='utf-8')) if cards_path.exists() else [],'video_available':(ROOT/'docs/DEMONSTRATION.webm').exists(),'documents':[{'id':'architecture','name':'Architecture et séquences'},{'id':'evolution','name':'Parcours 2.1 : observations et coordonnées'},{'id':'runbook','name':'Runbook RB-LLM-01'},{'id':'video','name':'Scénario de vidéo'},{'id':'demo','name':'Vidéo de démonstration enregistrée'},{'id':'validation','name':'Rapport des vérifications'},{'id':'readme','name':'Guide du projet'}]}

    @app.get('/documents/{document_id}')
    def document(document_id:str):
        paths={'architecture':ROOT/'docs/ARCHITECTURE_ET_PARCOURS.html','evolution':ROOT/'docs/EVOLUTION_2_1.md','runbook':ROOT/'docs/RUNBOOK.md','video':ROOT/'docs/DEMO_VIDEO.md','demo':ROOT/'docs/DEMONSTRATION.webm','validation':ROOT/'docs/VALIDATION.md','readme':ROOT/'README.md'}
        target=paths.get(document_id)
        if not target or not target.exists():
            raise HTTPException(404,'Document introuvable.')
        return FileResponse(target,media_type='text/html' if target.suffix=='.html' else 'video/webm' if target.suffix=='.webm' else 'text/plain; charset=utf-8')

    return app


app=create_app()
