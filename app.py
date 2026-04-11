from flask import Flask, render_template, request, redirect, session, make_response
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

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

def db_get(table, params=None):
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=HEADERS, params=params)
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        print("db_get error:", e)
        return []

def db_post(table, data):
    try:
        h = {**HEADERS, "Prefer": "return=representation"}
        r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=h, json=data)
        print(r.status_code, r.text)
    except Exception as e:
        print("db_post error:", e)

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
        print("Registering:", request.form['username'])
        db_post('users', {'username': request.form['username'], 'password': request.form['password']})
        print("Done")
        return redirect('/login')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()
            users = db_get('users', {'username': f'eq.{username}', 'password': f'eq.{password}'})
            print("Login result:", users)
            if users and len(users) > 0:
                session['user_id'] = users[0]['id']
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
