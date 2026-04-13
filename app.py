from flask import Flask, render_template, request, redirect, session, Response
from itsdangerous import URLSafeSerializer
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "libraspace2025")
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
)
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}


def supabase_config_error():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return "Supabase is not configured on this deployment yet."
    return None


def auth_page_context(error=None, success=None):
    return {
        "error": error,
        "success": success,
        "config_error": supabase_config_error()
    }


def explain_supabase_error(error):
    if isinstance(error, RuntimeError):
        return str(error)

    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)

    if status_code in (401, 403):
        return "Supabase rejected the request. Check your Vercel env vars and Row Level Security policies."
    if status_code == 404:
        return "Supabase table or endpoint was not found. Check the project URL and table names."
    if status_code == 409:
        return "That username already exists. Try another username."

    return "The app could not connect to Supabase right now."

def db_get(table, params=None):
    config_error = supabase_config_error()
    if config_error:
        raise RuntimeError(config_error)

    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=HEADERS, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        response_text = getattr(getattr(e, "response", None), "text", "")
        print("db_get error:", e, response_text)
        raise

def db_post(table, data):
    config_error = supabase_config_error()
    if config_error:
        raise RuntimeError(config_error)

    try:
        h = {**HEADERS, "Prefer": "return=representation"}
        r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=h, json=data, timeout=15)
        r.raise_for_status()
        print(r.status_code, r.text)
        return r.json()
    except Exception as e:
        response_text = getattr(getattr(e, "response", None), "text", "")
        print("db_post error:", e, response_text)
        raise

@app.route('/')
def home():
    return render_template('index.html', active_page='home')

@app.route('/features')
def features():
    return render_template('features.html', active_page='features')

@app.route('/about')
def about():
    return render_template('about.html', active_page='about')


@app.route('/favicon.png')
def favicon():
    return Response(status=204)



@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()

            if not username or not password:
                return render_template('register.html', **auth_page_context(error='Username and password are required.'))

            print("Registering:", username)
            db_post('users', {'username': username, 'password': password})
            print("Done")
            return render_template('login.html', **auth_page_context(success='Account created successfully. You can log in now.'))
        except Exception as e:
            print("Register error:", str(e))
            return render_template('register.html', **auth_page_context(error=explain_supabase_error(e)))
    return render_template('register.html', **auth_page_context())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()

            if not username or not password:
                return render_template('login.html', **auth_page_context(error='Username and password are required.'))

            users = db_get('users', {'username': f'eq.{username}', 'password': f'eq.{password}'})
            print("Login result:", users)
            if users and len(users) > 0:
                session['user_id'] = users[0]['id']
                session.modified = True
                return redirect('/dashboard')
            return render_template('login.html', **auth_page_context(error='Invalid username or password'))
        except Exception as e:
            print("Login error:", str(e))
            return render_template('login.html', **auth_page_context(error=explain_supabase_error(e)))
    return render_template('login.html', **auth_page_context())

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    try:
        genre_filter = request.args.get('genre')
        params = {'genre': f'eq.{genre_filter}'} if genre_filter else None
        books = db_get('books', params)
        all_books = db_get('books')
        genres = list(set(b.get('genre', 'General') for b in all_books if b.get('genre')))
        user = db_get('users', {'id': f"eq.{session['user_id']}"})
        username = user[0]['username'] if user else 'Reader'
        return render_template('dashboard.html', books=books, genres=genres, selected_genre=genre_filter, username=username)
    except Exception as e:
        print("Dashboard error:", str(e))
        return redirect('/login')

@app.route('/book/<int:book_id>')
def book_detail(book_id):
    if 'user_id' not in session:
        return redirect('/login')
    result = db_get('books', {'id': f'eq.{book_id}'})
    if not result:
        return redirect('/dashboard')
    user = db_get('users', {'id': f"eq.{session['user_id']}"})
    username = user[0]['username'] if user else 'Reader'
    return render_template('book_detail.html', book=result[0], username=username)

@app.route('/reserve/<int:book_id>')
def reserve(book_id):
    if 'user_id' not in session:
        return redirect('/login')
    db_post('bookings', {'user_id': session['user_id'], 'book_id': book_id})
    return redirect('/dashboard')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
