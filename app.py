from flask import Flask, render_template, request, redirect, session
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = "secret123"

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

@app.route('/')
def home():
    return redirect('/login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        supabase.table('users').insert({'username': username, 'password': password}).execute()
        return redirect('/login')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        result = supabase.table('users').select('*').eq('username', username).eq('password', password).execute()
        if result.data:
            session['user_id'] = result.data[0]['id']
            return redirect('/dashboard')
        return "Invalid login"
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    books = supabase.table('books').select('*').execute().data
    return render_template('dashboard.html', books=books)

@app.route('/book/<int:book_id>')
def book(book_id):
    if 'user_id' not in session:
        return redirect('/login')
    supabase.table('bookings').insert({'user_id': session['user_id'], 'book_id': book_id}).execute()
    return redirect('/dashboard')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__ == '__main__':
    app.run(debug=True)
