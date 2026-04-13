from flask import Flask, render_template, request, redirect, session
import requests
import os
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix
import psycopg
from psycopg.rows import dict_row

load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.secret_key = os.getenv("SECRET_KEY", "libraspace2025")
app.config['SESSION_COOKIE_SECURE'] = os.getenv("VERCEL") == "1"
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}


def get_db_connection():
    if not DATABASE_URL:
        return None
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def db_get(table, params=None):
    if DATABASE_URL:
        return []
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("db_get error: missing SUPABASE_URL or SUPABASE_KEY")
        return []
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=HEADERS, params=params)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        print("db_get error:", e)
        return []

def db_post(table, data):
    if DATABASE_URL:
        return []
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("db_post error: missing SUPABASE_URL or SUPABASE_KEY")
        return []
    try:
        h = {**HEADERS, "Prefer": "return=representation"}
        r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=h, json=data)
        r.raise_for_status()
        print(r.status_code, r.text)
        return r.json() if r.text else []
    except Exception as e:
        print("db_post error:", e)
        return []


def get_user_by_credentials(username, password):
    if DATABASE_URL:
        try:
            with get_db_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT id, username FROM users WHERE username = %s AND password = %s LIMIT 1",
                    (username, password),
                )
                return cur.fetchone()
        except Exception as e:
            print("get_user_by_credentials error:", e)
            return None

    users = db_get('users', {'username': f'eq.{username}', 'password': f'eq.{password}'})
    return users[0] if users else None


def get_user_by_id(user_id):
    if DATABASE_URL:
        try:
            with get_db_connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT id, username FROM users WHERE id = %s LIMIT 1", (user_id,))
                return cur.fetchone()
        except Exception as e:
            print("get_user_by_id error:", e)
            return None

    users = db_get('users', {'id': f"eq.{user_id}"})
    return users[0] if users else None


def create_user(username, password):
    if DATABASE_URL:
        try:
            with get_db_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, password) VALUES (%s, %s) RETURNING id, username",
                    (username, password),
                )
                user = cur.fetchone()
                conn.commit()
                return user
        except Exception as e:
            print("create_user error:", e)
            return None

    created = db_post('users', {'username': username, 'password': password})
    return created[0] if created else None


def get_books(genre_filter=None):
    if DATABASE_URL:
        try:
            with get_db_connection() as conn, conn.cursor() as cur:
                if genre_filter:
                    cur.execute("SELECT * FROM books WHERE genre = %s ORDER BY id", (genre_filter,))
                else:
                    cur.execute("SELECT * FROM books ORDER BY id")
                return cur.fetchall()
        except Exception as e:
            print("get_books error:", e)
            return []

    params = {'genre': f'eq.{genre_filter}'} if genre_filter else None
    return db_get('books', params)


def get_book_by_id(book_id):
    if DATABASE_URL:
        try:
            with get_db_connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT * FROM books WHERE id = %s LIMIT 1", (book_id,))
                return cur.fetchone()
        except Exception as e:
            print("get_book_by_id error:", e)
            return None

    books = db_get('books', {'id': f'eq.{book_id}'})
    return books[0] if books else None


def create_booking(user_id, book_id):
    if DATABASE_URL:
        try:
            with get_db_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO bookings (user_id, book_id) VALUES (%s, %s) RETURNING user_id, book_id",
                    (user_id, book_id),
                )
                booking = cur.fetchone()
                conn.commit()
                return booking
        except Exception as e:
            print("create_booking error:", e)
            return None

    created = db_post('bookings', {'user_id': user_id, 'book_id': book_id})
    return created[0] if created else None

@app.route('/')
def home():
    return render_template('index.html', active_page='home')

@app.route('/features')
def features():
    return render_template('features.html', active_page='features')

@app.route('/about')
def about():
    return render_template('about.html', active_page='about')



@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        print("Registering:", username)
        created_user = create_user(username, password)
        if not created_user:
            return render_template('register.html', error='Unable to create account right now. Please try again.')
        return redirect('/login')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()
            if not DATABASE_URL and (not SUPABASE_URL or not SUPABASE_KEY):
                return render_template('login.html', error='Server configuration error: missing database environment variables')
            user = get_user_by_credentials(username, password)
            print("Login result:", user)
            if user:
                session['user_id'] = user['id']
                session.modified = True
                return redirect('/dashboard')
            return render_template('login.html', error='Invalid username or password')
        except Exception as e:
            print("Login error:", str(e))
            return render_template('login.html', error='Something went wrong. Please try again.')
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    try:
        genre_filter = request.args.get('genre')
        books = get_books(genre_filter)
        all_books = get_books()
        genres = list(set(b.get('genre', 'General') for b in all_books if b.get('genre')))
        user = get_user_by_id(session['user_id'])
        username = user['username'] if user else 'Reader'
        return render_template('dashboard.html', books=books, genres=genres, selected_genre=genre_filter, username=username)
    except Exception as e:
        print("Dashboard error:", str(e))
        return redirect('/login')

@app.route('/book/<int:book_id>')
def book_detail(book_id):
    if 'user_id' not in session:
        return redirect('/login')
    book = get_book_by_id(book_id)
    if not book:
        return redirect('/dashboard')
    user = get_user_by_id(session['user_id'])
    username = user['username'] if user else 'Reader'
    return render_template('book_detail.html', book=book, username=username)

@app.route('/reserve/<int:book_id>')
def reserve(book_id):
    if 'user_id' not in session:
        return redirect('/login')
    create_booking(session['user_id'], book_id)
    return redirect('/dashboard')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
