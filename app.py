from flask import Flask, render_template, request, redirect, session
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = "secret123"

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

def db_get(table, params=None):
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=HEADERS, params=params)
    return r.json()

def db_post(table, data):
    h = {**HEADERS, "Prefer": "return=representation"}
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=h, json=data)
    print(r.status_code, r.text)

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
        users = db_get('users', {'username': f"eq.{request.form['username']}", 'password': f"eq.{request.form['password']}"})
        if users:
            session['user_id'] = users[0]['id']
            return redirect('/dashboard')
        return "Invalid login"
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    genre_filter = request.args.get('genre')
    params = {'genre': f'eq.{genre_filter}'} if genre_filter else None
    books = db_get('books', params)
    all_books = db_get('books')
    genres = list(set(b.get('genre', 'General') for b in all_books if b.get('genre')))
    user = db_get('users', {'id': f"eq.{session['user_id']}"})
    username = user[0]['username'] if user else 'Reader'
    return render_template('dashboard.html', books=books, genres=genres, selected_genre=genre_filter, username=username)

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
