import logging
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import create_app
from app.storage import Store

logging.disable(logging.CRITICAL)


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=str(Path(self.temp.name)/'test.sqlite')
        self.env=patch.dict(os.environ,{'OPENROUTER_API_KEY':'','OPENAI_API_KEY':'','LLM_PROVIDER':'openrouter','LLM_MODEL':'openai/gpt-4o-mini'})
        self.env.start()
        self.app=create_app(self.path)
        self.client=TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.env.stop()
        self.temp.cleanup()

    def create(self,code='P0301',**kwargs):
        response=self.client.post('/api/diagnostics',json={'code':code,**kwargs})
        self.assertEqual(response.status_code,202,response.text)
        return self.detail(response.json()['id'])

    def detail(self,run_id):
        return self.client.get('/api/diagnostics/'+run_id).json()

    def accept(self,run):
        response=self.client.post(f"/api/diagnostics/{run['id']}/quote-decision",json={'accepted':True})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def book(self,run,slot=None):
        return self.client.post(f"/api/diagnostics/{run['id']}/booking-decision",json={'confirmed':True,'slot':slot or run['slots'][0]})

    def test_two_real_human_interrupts_before_booking(self):
        run=self.create()
        self.assertEqual(run['status'],'awaiting_quote_approval')
        self.assertEqual(run['estimate']['total'],480)
        self.assertIsNone(run['appointment'])
        self.assertFalse(any(e['agent']=='rendez_vous' for e in run['events']))
        snapshot=self.app.state.engine.graph.get_state({'configurable':{'thread_id':run['id']}})
        self.assertEqual(snapshot.next,('quote_approval',))
        run=self.accept(run)
        self.assertEqual(run['status'],'awaiting_booking_approval')
        self.assertIsNone(run['appointment'])
        self.assertEqual(self.client.get('/api/appointments').json(),[])
        booked=self.book(run)
        self.assertEqual(booked.status_code,200,booked.text)
        self.assertEqual(booked.json()['status'],'booked')
        self.assertEqual(booked.json()['appointment']['slot'],run['slots'][0])

    def test_declining_price_skips_appointment_agent(self):
        run=self.create()
        result=self.client.post(f"/api/diagnostics/{run['id']}/quote-decision",json={'accepted':False}).json()
        self.assertEqual(result['status'],'price_declined')
        self.assertFalse(any(e['agent']=='rendez_vous' for e in result['events']))
        self.assertFalse(self.client.get('/api/appointments').json())

    def test_declining_booking_keeps_accepted_quote(self):
        run=self.accept(self.create())
        result=self.client.post(f"/api/diagnostics/{run['id']}/booking-decision",json={'confirmed':False}).json()
        self.assertEqual(result['status'],'booking_declined')
        self.assertEqual(result['price_decision'],'accepted')
        self.assertIsNone(result['appointment'])

    def test_unknown_code_is_graph_branch_not_http_failure(self):
        run=self.create('P0999')
        self.assertEqual(run['status'],'unknown_code')
        self.assertNotIn('estimate',run)
        self.assertFalse(any(e['agent']=='recherche' for e in run['events']))

    def test_validation_and_normalization(self):
        self.assertEqual(self.create('p0301')['code'],'P0301')
        for body in ({'code':'XXXXX'},{'code':'P0301','year':1800},{'code':'P0301','vehicle_id':'missing'},{'code':'P0301','scenario':'delete_database'}):
            self.assertEqual(self.client.post('/api/diagnostics',json=body).status_code,422)

    def test_all_ten_fixtures_have_consistent_estimates(self):
        codes=self.client.get('/api/codes').json()
        self.assertEqual(len(codes),10)
        for entry in codes:
            run=self.create(entry['code'])
            self.assertEqual(run['status'],'awaiting_quote_approval')
            cost=run['estimate']
            self.assertEqual(cost['total'],cost['parts']+cost['labor'])
            self.assertEqual(cost['labor'],round(cost['hours']*cost['hourly_rate']))

    def test_invalid_slot_preserves_interrupt(self):
        run=self.accept(self.create())
        result=self.book(run,'2030-01-01T09:00:00+01:00')
        self.assertEqual(result.status_code,422)
        self.assertEqual(self.detail(run['id'])['status'],'awaiting_booking_approval')

    def test_duplicate_booking_is_idempotent(self):
        run=self.accept(self.create())
        first=self.book(run)
        second=self.book(run)
        self.assertEqual(first.json()['appointment']['id'],second.json()['appointment']['id'])
        self.assertEqual(len(self.client.get('/api/appointments').json()),1)

    def test_conflict_then_reselect(self):
        first=self.accept(self.create())
        second=self.accept(self.create())
        slot=first['slots'][0]
        self.assertEqual(self.book(first,slot).status_code,200)
        self.assertEqual(self.book(second,slot).status_code,409)
        self.assertEqual(self.detail(second['id'])['status'],'awaiting_booking_approval')
        options=self.client.get(f"/api/diagnostics/{second['id']}/slots").json()
        self.assertNotIn(slot,options)
        self.assertEqual(self.book(second,options[0]).json()['status'],'booked')

    def test_simultaneous_confirmation_one_winner(self):
        first=self.accept(self.create())
        second=self.accept(self.create())
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda r:self.book(r,first['slots'][0]).status_code,[first,second]))
        self.assertEqual(sorted(results),[200,409])

    def test_repeated_quote_decision_is_rejected(self):
        run=self.create()
        self.accept(run)
        response=self.client.post(f"/api/diagnostics/{run['id']}/quote-decision",json={'accepted':False})
        self.assertEqual(response.status_code,409)

    def test_no_slots_branch(self):
        run=self.create()
        with patch.object(self.app.state.store,'slots',return_value=[]):
            result=self.accept(run)
        self.assertEqual(result['status'],'no_slots')
        self.assertIsNone(result['appointment'])

    def test_simulated_incident_has_runbook_and_fallback(self):
        run=self.create(scenario='openai_unavailable')
        self.assertEqual(run['status'],'awaiting_quote_approval')
        self.assertTrue(run['degraded'])
        incidents=self.client.get('/api/monitoring/incidents').json()
        self.assertEqual(len(incidents),2)
        self.assertTrue(all(i['status']=='mitigated' and i['runbook']=='RB-LLM-01' and i['simulated'] for i in incidents))
        self.assertFalse(run['metrics']['incomplete_usage'])
        self.assertEqual(self.client.get('/api/monitoring/summary').json()['runs'],0)
        self.assertEqual(self.client.get('/api/monitoring/summary?origin=scenario').json()['runs'],1)

    def test_successful_llm_is_not_repeated_on_resume(self):
        usage={'provider':'openrouter','model':'openai/gpt-4o-mini','input_tokens':100,'output_tokens':20,'cost_usd':.000027,'pricing_version':'2026-10-30'}
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test-only'}),patch('app.llm.generate',return_value=('Explication pédagogique conforme à la fiche fournie.',usage)) as generate:
            run=self.create()
            self.assertEqual(generate.call_count,2)
            self.assertEqual(run['metrics']['input_tokens'],200)
            self.assertAlmostEqual(run['metrics']['cost_usd'],.000054)
            run=self.accept(run)
            self.book(run)
            self.assertEqual(generate.call_count,2)

    def test_provider_error_is_visible_not_fatal(self):
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test-only'}),patch('app.llm.generate',side_effect=TimeoutError):
            run=self.create()
        self.assertTrue(run['degraded'])
        self.assertEqual(run['providers']['interpretation'],'fallback')
        self.assertFalse(self.client.get('/api/monitoring/incidents').json()[0]['simulated'])

    def test_correlation_id_and_monotonic_events(self):
        run=self.accept(self.create())
        result=self.book(run).json()
        self.assertTrue(all(e['correlation_id']==run['id'] for e in result['events']))
        self.assertEqual(len({e['id'] for e in result['events']}),len(result['events']))
        self.assertEqual(sum(e['kind']=='agent.completed' for e in result['events']),4)
        self.assertFalse(any(e['kind']=='agent.failed' for e in result['events']))
        incremental=self.client.get(f"/api/diagnostics/{run['id']}/events?after_event=7").json()
        self.assertTrue(all(e['id']>7 for e in incremental))

    def test_obdb_provenance_and_year_filters(self):
        run=self.create(vehicle_id='toyota-corolla-hybrid',year=2020)
        self.assertTrue(run['vehicle_signals'])
        self.assertTrue(all(len(s['source']['commit'])==40 for s in run['vehicle_signals']))
        old=self.create(vehicle_id='toyota-corolla-hybrid',year=1990)
        self.assertTrue(all(Store.applicable(s['filter'],1990) for s in old['vehicle_signals']))
        self.assertFalse(Store.applicable({'from':2019},2010))
        self.assertFalse(Store.applicable({'years':[2020]},2021))

    def test_checkpoint_survives_application_recreation(self):
        run=self.create()
        # Une seconde instance sur le même fichier reprend le checkpoint suspendu.
        with TestClient(create_app(self.path)) as other:
            response=other.post(f"/api/diagnostics/{run['id']}/quote-decision",json={'accepted':True})
            self.assertEqual(response.json()['status'],'awaiting_booking_approval')

    def test_export_calendar_static_and_unknown_documents(self):
        run=self.accept(self.create())
        booked=self.book(run).json()
        exported=self.client.get(f"/api/diagnostics/{run['id']}/export")
        self.assertEqual(exported.json()['correlation_id'],run['id'])
        calendar=self.client.get('/api/appointments/'+booked['appointment']['id']+'/calendar')
        self.assertIn('BEGIN:VCALENDAR',calendar.text)
        for path in ['/','/api/health','/static/app.js','/static/styles.css','/static/assets/chart.umd.min.js','/static/assets/hologram-car.png']:
            self.assertEqual(self.client.get(path).status_code,200,path)
        self.assertEqual(self.client.get('/api/diagnostics/missing').status_code,404)
        self.assertEqual(self.client.get('/documents/missing').status_code,404)
        project=self.client.get('/api/project').json()
        self.assertEqual(len(project['cards']),5)
        self.assertTrue(project['video_available'])
        for path in ['/documents/validation','/documents/runbook','/documents/demo']:
            self.assertEqual(self.client.get(path).status_code,200,path)


if __name__=='__main__':
    unittest.main()
