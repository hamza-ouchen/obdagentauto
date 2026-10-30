"""Quatre agents métier, deux pauses humaines et monitoring transversal."""
import json
import logging
import sqlite3
from threading import RLock
from time import perf_counter
from typing import TypedDict
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from app import llm

LOGGER=logging.getLogger('autodiag')
AGENTS=('interpretation','recherche','estimation','rendez_vous')
WAITING={'quote_approval':'awaiting_quote_approval','booking_approval':'awaiting_booking_approval'}


class DiagnosticState(TypedDict,total=False):
    id:str
    correlation_id:str
    code:str
    vehicle:str
    vehicle_id:str|None
    year:int|None
    known_code:bool
    interpretation:str
    title:str
    system:str
    causes:list[dict]
    research_summary:str
    vehicle_signals:list[dict]
    estimate:dict
    price_decision:str
    slots:list[str]
    appointment:dict|None
    booking_decision:str
    status:str
    providers:dict
    degraded:bool
    scenario:str|None


class Engine:
    def __init__(self,store):
        self.store=store
        self.guard=RLock()
        self.active=set()
        self.checkpoint_db=sqlite3.connect(store.path,check_same_thread=False,timeout=20)
        self.saver=SqliteSaver(self.checkpoint_db)
        builder=StateGraph(DiagnosticState)
        for name in AGENTS:
            builder.add_node(name,self.observed(name,getattr(self,name)))
        builder.add_node('quote_approval',self.quote_approval)
        builder.add_node('booking_approval',self.booking_approval)
        builder.add_edge(START,'interpretation')
        builder.add_conditional_edges('interpretation',lambda s:'recherche' if s['known_code'] else END)
        builder.add_edge('recherche','estimation')
        builder.add_edge('estimation','quote_approval')
        builder.add_conditional_edges('quote_approval',lambda s:'rendez_vous' if s['price_decision']=='accepted' else END)
        builder.add_conditional_edges('rendez_vous',lambda s:'booking_approval' if s['slots'] else END)
        builder.add_edge('booking_approval',END)
        self.graph=builder.compile(checkpointer=self.saver)

    def emit(self,run_id,agent,kind,**payload):
        event=self.store.event(run_id,agent,kind,**payload)
        LOGGER.info(json.dumps(event,ensure_ascii=False))
        return event

    def observed(self,agent,function):
        def node(state):
            started=perf_counter()
            self.store.merge(state['id'],{'current_agent':agent,'status':'running'})
            self.emit(state['id'],agent,'agent.started')
            try:
                result=function(state)
            except Exception as exc:
                self.emit(state['id'],agent,'agent.failed',duration_ms=round((perf_counter()-started)*1000),error_category=type(exc).__name__)
                raise
            usage=result.pop('_usage',{'input_tokens':0,'output_tokens':0,'cost_usd':0})
            self.emit(state['id'],agent,'agent.completed',duration_ms=round((perf_counter()-started)*1000),**usage)
            return result
        return node

    def language(self,state,agent,context,fallback):
        config=llm.provider_config()
        providers=dict(state.get('providers',{}))
        if not config['key'] and not state.get('scenario'):
            providers[agent]='demo'
            return fallback,{'providers':providers},{'input_tokens':0,'output_tokens':0,'cost_usd':0,'provider':'demo'}
        try:
            if state.get('scenario')=='openai_unavailable':
                raise ConnectionError('simulated_provider_unavailable')
            text,usage=llm.generate(agent,context)
            providers[agent]=config['provider']
            return text,{'providers':providers},usage
        except Exception as exc:
            self.emit(state['id'],agent,'provider.error',error_category=type(exc).__name__,simulated=bool(state.get('scenario')))
            incident=self.store.incident(state['id'],agent,type(exc).__name__,bool(state.get('scenario')))
            self.store.mitigate(incident)
            self.emit(state['id'],agent,'fallback.applied',incident_id=incident['id'])
            providers[agent]='fallback'
            simulated=bool(state.get('scenario'))
            return fallback,{'providers':providers,'degraded':True},{'provider':'fallback','input_tokens':0 if simulated else None,'output_tokens':0 if simulated else None,'cost_usd':0 if simulated else None,'model':config['model']}

    def interpretation(self,state):
        entry=self.store.code(state['code'])
        if not entry:
            self.emit(state['id'],'interpretation','code.unknown')
            return {'known_code':False,'status':'unknown_code','title':'Code non couvert','interpretation':'Ce code n’est pas présent dans les fiches du TP. Choisissez un code disponible.'}
        text,meta,usage=self.language(state,'interpretation',{'code':state['code'],'definition':entry['description']},entry['description'])
        return {'known_code':True,'title':entry['title'],'system':entry['system'],'interpretation':text,**meta,'_usage':usage}

    def recherche(self,state):
        causes=self.store.code(state['code'])['causes']
        text,meta,usage=self.language(state,'recherche',{'code':state['code'],'causes':[{'name':c['name'],'control':c['detail']} for c in causes]},'Contrôler d’abord la première hypothèse, puis les causes alternatives. Ces pistes nécessitent une vérification en atelier.')
        vehicles=self.store.vehicles(state.get('year'),state.get('vehicle_id')) if state.get('vehicle_id') else []
        return {'causes':[{**c,'source':f"Fiche pédagogique SQLite · {state['code']}"} for c in causes],'research_summary':text,'vehicle_signals':vehicles[0]['signals'][:12] if vehicles else [],**meta,'_usage':usage}

    def estimation(self,state):
        entry=self.store.code(state['code'])
        parts,hours,rate=entry['causes'][0]['parts'],entry['hours'],200
        return {'estimate':{'parts':parts,'hours':hours,'hourly_rate':rate,'labor':round(hours*rate),'total':parts+round(hours*rate),'currency':'DH','repair':state['causes'][0]['name'],'note':'Prix fictifs du TP. Une seule hypothèse chiffrée, à confirmer après contrôle. Les causes ne sont pas cumulées.'}}

    def quote_approval(self,state):
        decision=interrupt({'kind':'quote_approval','estimate':state['estimate']})
        accepted=decision.get('accepted') is True
        self.emit(state['id'],'monitoring','quote.accepted' if accepted else 'price.declined')
        return {'price_decision':'accepted' if accepted else 'declined','status':'running' if accepted else 'price_declined'}

    def rendez_vous(self,state):
        slots=self.store.slots()
        return {'slots':slots,'status':'running' if slots else 'no_slots'}

    def booking_approval(self,state):
        decision=interrupt({'kind':'booking_approval','slots':state['slots']})
        if decision.get('confirmed') is not True:
            self.emit(state['id'],'monitoring','booking.declined')
            return {'booking_decision':'declined','status':'booking_declined','appointment':None}
        appointment=self.store.book(state['id'],decision['slot'])
        self.emit(state['id'],'rendez_vous','booking.confirmed',appointment_id=appointment['id'])
        return {'appointment':appointment,'booking_decision':'confirmed','status':'booked'}

    def claim(self,run_id):
        with self.guard:
            if run_id in self.active:
                return False
            self.active.add(run_id)
            return True

    def execute(self,run_id,decision=None):
        started=perf_counter()
        try:
            state=self.store.get(run_id)
            initial={k:v for k,v in state.items() if k in DiagnosticState.__annotations__}
            self.emit(run_id,'monitoring','run.started' if decision is None else 'human.wait.ended')
            for update in self.graph.stream(initial if decision is None else Command(resume=decision),{'configurable':{'thread_id':run_id}},stream_mode='updates'):
                for node,result in update.items():
                    if node!='__interrupt__' and isinstance(result,dict):
                        self.store.merge(run_id,result)
            snapshot=self.graph.get_state({'configurable':{'thread_id':run_id}})
            patch=dict(snapshot.values)
            if snapshot.next:
                patch['status']=WAITING[snapshot.next[0]]
                self.emit(run_id,'monitoring','human.wait.started',wait_kind=snapshot.next[0])
            else:
                self.emit(run_id,'monitoring','run.completed',outcome=patch.get('status'))
            self.store.merge(run_id,{**patch,'processing_ms':state.get('processing_ms',0)+round((perf_counter()-started)*1000),'current_agent':None})
        except Exception as exc:
            self.emit(run_id,'monitoring','run.failed',error_category=type(exc).__name__)
            self.store.merge(run_id,{'status':'failed','current_agent':None,'error':'Erreur technique pendant le traitement. Consultez les traces avec cet identifiant.'})
        finally:
            with self.guard:
                self.active.discard(run_id)

    def close(self):
        self.checkpoint_db.close()
