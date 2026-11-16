"""Local, single-user Agile Tracker. Story API and SQLite storage."""
import json
import os
import sqlite3
from datetime import datetime, timezone
from contextlib import contextmanager

from flask import Flask, jsonify, request, render_template
from werkzeug.exceptions import HTTPException

STATUSES = ('todo', 'doing', 'done')


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def validate(data):
    if not isinstance(data, dict):
        raise ValueError('Sisend peab olema JSON objekt.')
    title = data.get('title')
    description = data.get('description', '')
    points = data.get('points')
    criteria = data.get('acceptanceCriteria')
    status = data.get('status', 'todo')
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ValueError('Pealkiri on kohustuslik ja võib olla kuni 200 märki.')
    if not isinstance(description, str) or len(description) > 10000:
        raise ValueError('Kirjeldus peab olema kuni 10000 märki.')
    if type(points) is not int or points < 0 or points > 1000000:
        raise ValueError('Punktid peavad olema täisarv vahemikus 0–1000000; tühi väärtus ei sobi.')
    if status not in STATUSES:
        raise ValueError('Staatus peab olema todo, doing või done.')
    if (not isinstance(criteria, list) or not criteria or len(criteria) > 100
            or any(not isinstance(c, str) or not c.strip() or len(c) > 2000 for c in criteria)):
        raise ValueError('Lisa vähemalt üks mittetühi vastuvõtutingimus (kuni 2000 märki).')
    return title.strip(), description.strip(), status, points, json.dumps([c.strip() for c in criteria])


def create_app(database=None):
    app = Flask(__name__)
    path = str(database or os.environ.get('TRACKER_DB', 'tracker.sqlite3'))
    app.config['MAX_CONTENT_LENGTH'] = 256 * 1024

    @contextmanager
    def connect():
        db = sqlite3.connect(path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS stories (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          title TEXT NOT NULL, description TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('todo','doing','done')),
          points INTEGER NOT NULL CHECK(points >= 0), priority INTEGER NOT NULL,
          criteria TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS comments (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          story_id INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
          text TEXT NOT NULL, created_at TEXT NOT NULL
        );
        ''')

    def story(db, identifier):
        row = db.execute('SELECT * FROM stories WHERE id=?', (identifier,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result['acceptanceCriteria'] = json.loads(result.pop('criteria'))
        result['createdAt'] = result.pop('created_at')
        result['updatedAt'] = result.pop('updated_at')
        result['comments'] = [dict(c) for c in db.execute(
            'SELECT id,text,created_at AS createdAt FROM comments WHERE story_id=? ORDER BY id',
            (identifier,))]
        return result

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.route('/api/stories', methods=['GET', 'POST'])
    def collection():
        with connect() as db:
            if request.method == 'GET':
                ids = db.execute('SELECT id FROM stories ORDER BY priority,id').fetchall()
                return jsonify([story(db, row['id']) for row in ids])
            values = validate(request.get_json())
            now = timestamp()
            priority = db.execute('SELECT COALESCE(MAX(priority),0)+1 FROM stories').fetchone()[0]
            cursor = db.execute('''INSERT INTO stories(title,description,status,points,criteria,
                                priority,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)''',
                                (*values, priority, now, now))
            result = story(db, cursor.lastrowid)
            return jsonify(result), 201, {'Location': f"/api/stories/{result['id']}"}

    @app.route('/api/stories/<int:identifier>', methods=['GET', 'PUT', 'DELETE'])
    def item(identifier):
        with connect() as db:
            current = story(db, identifier)
            if current is None:
                return jsonify(error='Sellist lugu ei leitud.'), 404
            if request.method == 'GET':
                return jsonify(current)
            if request.method == 'DELETE':
                db.execute('DELETE FROM stories WHERE id=?', (identifier,))
                return '', 204
            values = validate(request.get_json())
            db.execute('''UPDATE stories SET title=?,description=?,status=?,points=?,criteria=?,
                          updated_at=? WHERE id=?''', (*values, timestamp(), identifier))
            return jsonify(story(db, identifier))

    @app.patch('/api/stories/<int:identifier>/status')
    def change_status(identifier):
        data = request.get_json()
        if not isinstance(data, dict) or data.get('status') not in STATUSES:
            raise ValueError('Staatus peab olema todo, doing või done.')
        with connect() as db:
            if story(db, identifier) is None:
                return jsonify(error='Sellist lugu ei leitud.'), 404
            db.execute('UPDATE stories SET status=?,updated_at=? WHERE id=?',
                       (data['status'], timestamp(), identifier))
            return jsonify(story(db, identifier))

    @app.post('/api/stories/<int:identifier>/comments')
    def add_comment(identifier):
        data = request.get_json()
        text = data.get('text') if isinstance(data, dict) else None
        if not isinstance(text, str) or not text.strip() or len(text) > 10000:
            raise ValueError('Kommentaar peab sisaldama 1–10000 märki.')
        with connect() as db:
            if story(db, identifier) is None:
                return jsonify(error='Sellist lugu ei leitud.'), 404
            now = timestamp()
            cursor = db.execute('INSERT INTO comments(story_id,text,created_at) VALUES(?,?,?)',
                                (identifier, text.strip(), now))
            db.execute('UPDATE stories SET updated_at=? WHERE id=?', (now, identifier))
            return jsonify(id=cursor.lastrowid, text=text.strip(), createdAt=now), 201

    @app.get('/')
    def board():
        return render_template('index.html')

    return app


if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=5055, debug=False)
