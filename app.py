from flask import Flask, render_template, request, redirect, session, Response
import requests
import os
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv(dotenv_path=".env")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "libraspace2025")
app.config['SESSION_COOKIE_SECURE'] = os.getenv("VERCEL_ENV") is not None
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
HTTP = requests.Session()
HTTP.trust_env = False


def supabase_config_error():
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_KEY:
        missing.append("SUPABASE_KEY")

    if missing:
        return "Supabase is not configured on this deployment yet. Missing: " + ", ".join(missing)
    return None


def auth_page_context(error=None, success=None, debug_hint=None):
    return {
        "error": error,
        "success": success,
        "config_error": supabase_config_error(),
        "debug_hint": debug_hint
    }


def explain_supabase_error(error):
    if isinstance(error, RuntimeError):
        return str(error)

    if isinstance(error, requests.exceptions.ProxyError):
        return "The app is using a broken proxy setting. Clear HTTP_PROXY, HTTPS_PROXY, and ALL_PROXY or bypass proxies for Supabase."
    if isinstance(error, requests.exceptions.Timeout):
        return "Supabase took too long to respond. Please try again in a moment."
    if isinstance(error, requests.exceptions.ConnectionError):
        return "The app could not reach Supabase over the network. Check proxy settings and outbound internet access."

    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    response_text = (getattr(response, "text", "") or "").lower()

    if status_code in (401, 403):
        if "row-level security" in response_text:
            return "Supabase blocked this request with Row Level Security. Add the needed SELECT, INSERT, and UPDATE policies for your tables."
        if "invalid api key" in response_text or "invalid jwt" in response_text:
            return "Supabase rejected the API key. Recheck SUPABASE_KEY in Vercel and redeploy."
        return "Supabase rejected the request. Check your Vercel env vars and Row Level Security policies."
    if status_code == 404:
        return "Supabase table or endpoint was not found. Check SUPABASE_URL and make sure the users, books, and bookings tables exist."
    if status_code == 409:
        return "That username already exists. Try another username."
    if status_code == 400:
        return "Supabase rejected the request format. Check your table columns and data types."
    if status_code and status_code >= 500:
        return "Supabase had a server-side error. Please try again in a moment."

    return "The app could not connect to Supabase right now."

def build_debug_hint(error):
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    response_text = (getattr(response, "text", "") or "").strip()
    error_name = type(error).__name__

    if response_text:
        response_text = response_text.replace("\n", " ").replace("\r", " ")
        response_text = response_text[:220]

    if status_code and response_text:
        return f"{error_name} ({status_code}): {response_text}"
    if status_code:
        return f"{error_name} ({status_code})"
    if response_text:
        return f"{error_name}: {response_text}"

    message = str(error).strip()
    if message:
        return f"{error_name}: {message[:220]}"

    return error_name

def db_get(table, params=None):
    config_error = supabase_config_error()
    if config_error:
        raise RuntimeError(config_error)

    try:
        r = HTTP.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=HEADERS, params=params, timeout=15)
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
        r = HTTP.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=h, json=data, timeout=15)
        r.raise_for_status()
        print(r.status_code, r.text)
        return r.json()
    except Exception as e:
        response_text = getattr(getattr(e, "response", None), "text", "")
        print("db_post error:", e, response_text)
        raise

def db_patch(table, data, params=None):
    config_error = supabase_config_error()
    if config_error:
        raise RuntimeError(config_error)

    try:
        h = {**HEADERS, "Prefer": "return=representation"}
        r = HTTP.patch(f"{SUPABASE_URL}/rest/v1/{table}", headers=h, params=params, json=data, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        response_text = getattr(getattr(e, "response", None), "text", "")
        print("db_patch error:", e, response_text)
        raise

def password_matches(stored_password, plain_password):
    if not stored_password:
        return False

    try:
        if stored_password.startswith(("pbkdf2:", "scrypt:")):
            return check_password_hash(stored_password, plain_password)
    except ValueError:
        return False

    return stored_password == plain_password

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
            password_hash = generate_password_hash(password)
            db_post('users', {'username': username, 'password': password_hash})
            print("Done")
            return render_template('login.html', **auth_page_context(success='Account created successfully. You can log in now.'))
        except Exception as e:
            print("Register error:", str(e))
            return render_template('register.html', **auth_page_context(error=explain_supabase_error(e), debug_hint=build_debug_hint(e)))
    return render_template('register.html', **auth_page_context())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()

            if not username or not password:
                return render_template('login.html', **auth_page_context(error='Username and password are required.'))

            users = db_get('users', {'username': f'eq.{username}'})
            print("Login result:", users)
            if users and len(users) > 0 and password_matches(users[0].get('password'), password):
                user = users[0]
                if user.get('password') == password:
                    db_patch('users', {'password': generate_password_hash(password)}, {'id': f"eq.{user['id']}"})
                session['user_id'] = user['id']
                session.modified = True
                return redirect('/dashboard')
            return render_template('login.html', **auth_page_context(error='Invalid username or password'))
        except Exception as e:
            print("Login error:", str(e))
            return render_template('login.html', **auth_page_context(error=explain_supabase_error(e), debug_hint=build_debug_hint(e)))
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
