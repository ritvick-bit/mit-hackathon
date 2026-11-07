"""Concurrent contractor/PM workflows share one project state without switching screens."""
import base64
import copy
import json
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from server import Application, Handler
from storage import Conflict, Store


class ContractorAPIIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.auth = patch('llm.runtime_status', return_value={'authenticated':False,'detail':'test'})
        self.auth.start()
        self.app = Application(self.tmp.name + '/contractor.sqlite3')
        self.token = self.app.contractor_login('electrician')['token']

    def tearDown(self):
        self.app.pool.shutdown(wait=True)
        self.auth.stop()
        self.tmp.cleanup()

    def report(self, project_id='millbrook_cold_storage', **action):
        payload = dict(type='report_problem',task_id='t_electrical',client_report_id='report-api-0001',
                       subject='Field obstruction',raw_text='Cable route is obstructed. Please arrange an engineering review.',urgency=2)
        payload.update(action)
        return self.app.contractor_action(self.token, {'project_id':project_id,
            'expected_project_version':self.app.store.projects()[project_id]['project_version'],'action':payload})

    def test_report_does_not_switch_or_overwrite_other_pm_project(self):
        before = self.app.store.read()
        revision = self.app.store.portfolio_revision()
        result = self.report()
        self.assertEqual(before, self.app.store.read())
        self.assertNotEqual(revision, result['portfolio_revision'])
        current = self.app.bootstrap('millbrook_cold_storage')
        self.assertEqual(current['workspace']['contractor_requests'][0]['priority'],85)
        self.assertIn('Cable route', current['workspace']['contractor_requests'][0]['message']['text'])
        self.assertEqual(-1,current['session_version'])
        self.assertEqual(before, self.app.store.read())
        restored = Store(self.app.store.path).projects()['millbrook_cold_storage']
        self.assertEqual(1,len(restored['state']['contractor_reports']))

    def test_same_project_update_invalidates_pm_screen_and_stale_contractor_write(self):
        before = self.app.store.read()
        old = self.app.store.projects()['harbor_components']
        self.report('harbor_components')
        self.assertGreater(self.app.store.read()['version'],before['version'])
        with self.assertRaises(Conflict):
            self.app.store.write_project(old['state'],old['project_version'])
        with self.assertRaises(Conflict):
            self.app.mutate('/api/messages',{'expected_version':before['version'],'sender_id':'electrician','raw_text':'stale'})

    def test_identity_and_authority_come_from_session(self):
        before = self.app.store.projects()
        with self.assertRaises(PermissionError):
            self.app.contractor_login('pm')
        with self.assertRaises(PermissionError):
            self.app.contractor_action('invalid',{})
        with self.assertRaises(Exception):
            self.report(type='approve_and_commit',actor_id='pm')
        with self.assertRaises(Exception):
            self.report(task_id='t_unload',actor_id='rigger')
        self.assertEqual(before,self.app.store.projects())

    def test_world_upgrade_preserves_submitted_report(self):
        self.report()
        current = self.app.store.projects()['millbrook_cold_storage']
        newer = copy.deepcopy(current['state'])
        newer['project']['world_version'] = 'future-world'
        self.assertEqual([], self.app.store.refresh_pristine_projects([newer]))
        self.assertEqual(current, self.app.store.projects()['millbrook_cold_storage'])

    def test_retry_does_not_duplicate_report_and_original_photo_is_scoped(self):
        encoded='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a92kAAAAASUVORK5CYII='
        args={'attachments':[{'name':'field.png','mime_type':'image/png','data_base64':encoded}]}
        self.report(**args)
        first=self.app.store.projects()['millbrook_cold_storage']
        self.report(**args)
        self.assertEqual(first,self.app.store.projects()['millbrook_cold_storage'])
        report=first['state']['contractor_reports'][0]
        message=next(m for m in first['state']['operations']['messages'] if m['id']==report['message_id'])
        identity=message['attachments'][0]['id']
        self.assertEqual(base64.b64decode(encoded),self.app.contractor_attachment(self.token,'millbrook_cold_storage',identity)['data'])
        rigger=self.app.contractor_login('rigger')['token']
        with self.assertRaises(PermissionError):
            self.app.contractor_attachment(rigger,'millbrook_cold_storage',identity)
        with self.assertRaises(Exception):
            self.report(raw_text='Different content',**args)
        self.assertEqual(first,self.app.store.projects()['millbrook_cold_storage'])

    def test_support_request_is_visible_as_pm_case_without_approving_it(self):
        before=copy.deepcopy(self.app.store.projects()['millbrook_cold_storage']['state'])
        self.report(support={'capability':'electrical_ct','mode':'before','duration_hours':4})
        state=self.app.store.projects()['millbrook_cold_storage']['state']
        report=state['contractor_reports'][0]
        case=next(c for c in state['operations']['cases'] if c['id']==report['case_id'])
        self.assertIn(report['message_id'],case['source_message_ids'])
        self.assertTrue(any(i['case_id']==case['id'] for i in state['operations']['inquiries']))
        self.assertEqual([(t['id'],t['planned_start'],t['status']) for t in before['tasks']],
                         [(t['id'],t['planned_start'],t['status']) for t in state['tasks']])
        self.assertTrue(all(state['gates'][key] == value for key,value in before['gates'].items()))
        self.assertFalse(any(g.get('status') == 'approved' for key,g in state['gates'].items() if key not in before['gates']))
        self.assertEqual(before['project']['budget'],state['project']['budget'])

    def test_async_summary_persists_to_its_project_after_pm_switch(self):
        started,finish=threading.Event(),threading.Event()
        def slow_summary(state,message,attachments):
            started.set(); finish.wait(3)
            return {'test':True}
        def apply_summary(state,identity,output,profiles):
            result=copy.deepcopy(state)
            next(m for m in result['operations']['messages'] if m['id']==identity)['summary']='Scoped live summary'
            return result
        self.app.auth['authenticated']=True
        with patch('llm.summarize_message',side_effect=slow_summary),patch('messages.apply_analysis',side_effect=apply_summary):
            result=self.report()
            job=result['summary_job']['job_id']
            self.assertTrue(started.wait(1))
            self.app.store.activate_project('riverbend_logistics',self.app.store.read()['version'])
            finish.set()
            for _ in range(200):
                if self.app.jobs[job]['status']!='running':break
                time.sleep(.01)
        self.assertEqual('completed',self.app.jobs[job]['status'])
        self.assertEqual('riverbend_logistics',self.app.store.read()['state']['project']['demo_project_id'])
        self.assertIn('Scoped live summary',json.dumps(self.app.store.projects()['millbrook_cold_storage']['state']))
        self.assertNotIn('Scoped live summary',json.dumps(self.app.store.read()['state']))

    def test_http_contract_requires_token_and_rejects_foreign_origin(self):
        class Quiet(Handler):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Quiet);server.app=self.app
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        client=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
        try:
            client.request('GET','/api/contractor/bootstrap')
            response=client.getresponse();self.assertEqual(403,response.status);response.read()
            client.request('GET','/api/contractor/bootstrap',headers={'Authorization':'Bearer '+self.token})
            response=client.getresponse();self.assertEqual(200,response.status)
            body=response.read().decode();self.assertNotIn('demo_response',body)
            client.request('POST','/api/contractor/login',json.dumps({'actor_id':'electrician'}),headers={'Content-Type':'application/json','Origin':'https://foreign.example'})
            response=client.getresponse();self.assertEqual(403,response.status);response.read()
        finally:
            client.close();server.shutdown();server.server_close()
