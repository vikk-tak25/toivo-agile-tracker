from contextlib import closing
from datetime import datetime
import sqlite3
import tempfile
import unittest
from pathlib import Path
from app import create_app


class StoryAPI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'stories.db'
        self.client = create_app(self.path).test_client()
        self.data = dict(title='Kasta basiilikut', description='Iga nädal', points=3,
                         acceptanceCriteria=['Muld on niiske.'])

    def tearDown(self):
        self.temp.cleanup()

    def add(self, **changes):
        return self.client.post('/api/stories', json=self.data | changes)

    def test_crud_and_restart(self):
        response = self.add()
        self.assertEqual(response.status_code, 201)
        identifier = response.json['id']
        self.assertEqual(self.client.get(response.headers['Location']).json['points'], 3)
        other = create_app(self.path).test_client()
        self.assertEqual(other.get('/api/stories').json[0]['id'], identifier)
        self.assertEqual(other.put(f'/api/stories/{identifier}', json=self.data | dict(points=0)).json['points'], 0)
        self.assertEqual(other.delete(f'/api/stories/{identifier}').status_code, 204)
        self.assertEqual(other.get(f'/api/stories/{identifier}').status_code, 404)

    def test_status_changes_and_restart(self):
        identifier = self.add().json['id']
        url = f'/api/stories/{identifier}/status'
        for status in ['doing', 'done', 'todo']:
            response = self.client.patch(url, json={'status': status})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['status'], status)
            self.assertEqual(response.json['title'], self.data['title'])
            self.assertEqual(create_app(self.path).test_client().get(
                f'/api/stories/{identifier}').json['status'], status)
        for data in [{}, [], {'status': 'invalid'}, {'status': None}]:
            self.assertEqual(self.client.patch(url, json=data).status_code, 400)
        self.assertEqual(self.client.patch('/api/stories/999/status',
                         json={'status': 'done'}).status_code, 404)

    def test_comments_persist_and_cascade(self):
        identifier = self.add().json['id']
        url = f'/api/stories/{identifier}/comments'
        response = self.client.post(url, json={'text': '  Arutame homme.  '})
        self.assertEqual(response.status_code, 201)
        comment = response.json
        self.assertEqual(comment['text'], 'Arutame homme.')
        self.assertEqual(datetime.fromisoformat(comment['createdAt']).utcoffset().total_seconds(), 0)
        other = create_app(self.path).test_client()
        self.assertEqual(other.get(f'/api/stories/{identifier}').json['comments'], [comment])
        second = other.post(url, json={'text': 'Valmis.'}).json
        self.assertGreater(second['id'], comment['id'])
        for data in [{}, [], {'text': ''}, {'text': '  '}, {'text': 1}, {'text': 'x' * 10001}]:
            self.assertEqual(other.post(url, json=data).status_code, 400)
        self.assertEqual(other.post('/api/stories/999/comments', json={'text': 'Tere'}).status_code, 404)
        self.assertEqual(other.delete(f'/api/stories/{identifier}').status_code, 204)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM comments').fetchone()[0], 0)

    def test_bad_points(self):
        for value in [None, '', -1, 1.5, True, '3', 1000001]:
            with self.subTest(value=value):
                self.assertEqual(self.add(points=value).status_code, 400)
        self.assertEqual(self.client.get('/api/stories').json, [])

    def test_required_fields(self):
        for changes in [dict(title=' '), dict(acceptanceCriteria=[]),
                        dict(acceptanceCriteria=[' ']), dict(status='invalid')]:
            self.assertEqual(self.add(**changes).status_code, 400)

    def test_bad_json_and_missing_routes(self):
        self.assertEqual(self.client.post('/api/stories', data='bad', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.get('/api/stories/123').status_code, 404)
        self.assertEqual(self.client.post('/api/stories', json=[]).status_code, 400)


if __name__ == '__main__':
    unittest.main(verbosity=2)
