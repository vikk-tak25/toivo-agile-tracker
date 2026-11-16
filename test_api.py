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
