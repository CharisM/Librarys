from flask import Flask, render_template, request, redirect, session, Response
import requests
import os
import random
import time
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash
from flask_mail import Mail, Message

load_dotenv(dotenv_path=".env")

def clean_env(name, default=None):
    value = os.getenv(name, default)
    if value is None:
        return None
    return value.strip().strip("\"'").strip()

app = Flask(__name__)
app.secret_key = clean_env("SECRET_KEY", "libraspace2025")
app.config['SESSION_COOKIE_SECURE'] = os.getenv("VERCEL_ENV") is not None
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = clean_env('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = clean_env('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = clean_env('MAIL_USERNAME')
mail = Mail(app)
CONTACT_RECIPIENT = clean_env('CONTACT_RECIPIENT') or clean_env('MAIL_USERNAME')

SUPABASE_URL = clean_env("SUPABASE_URL") or clean_env("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = (
    clean_env("SUPABASE_SERVICE_ROLE_KEY")
    or clean_env("SUPABASE_KEY")
    or clean_env("SUPABASE_ANON_KEY")
    or clean_env("NEXT_PUBLIC_SUPABASE_ANON_KEY")
)
ADMIN_USERNAME = clean_env("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = clean_env("ADMIN_PASSWORD", "admin1234")
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}
HTTP = requests.Session()
HTTP.trust_env = False
HTTP.verify = False

DEFAULT_BOOK_IMAGES = {
    "the notebook": "/static/img/THENOTEBOOK.jpg",
    "me before you": "/static/img/MEBEFOREYOU.jpg",
    "a walk to remember": "/static/img/AWALKTOREMEMBER.jpg",
    "ugly love": "/static/img/UGLYLOVE.jpg",
    "the great gatsby": "/static/img/THEGREATGATSBY.jpg",
    "to kill a mockingbird": "/static/img/TOKILLAMOCKINGBIRD.jpg",
    "the little prince": "/static/img/THELITTLEPRINCE.jpg",
    "pride and prejudice": "https://images.unsplash.com/photo-1512820790803-83ca734da794?auto=format&fit=crop&w=800&q=80",
    "dune": "https://images.unsplash.com/photo-1516979187457-637abb4f9353?auto=format&fit=crop&w=800&q=80",
    "harry potter and the sorcerer's stone": "https://images.unsplash.com/photo-1521587760476-6c12a4b040da?auto=format&fit=crop&w=800&q=80",
    "the hobbit": "https://images.unsplash.com/photo-1495446815901-a7297e633e8d?auto=format&fit=crop&w=800&q=80",
    "clean code": "https://images.unsplash.com/photo-1515879218367-8466d910aaa4?auto=format&fit=crop&w=800&q=80",
    "database system concepts": "https://images.unsplash.com/photo-1555066931-4365d14bab8c?auto=format&fit=crop&w=800&q=80",
    "python physics": "https://i.pinimg.com/1200x/87/80/58/878058896f04c77929c99fda64493ba0.jpg",
    "python basics": "https://i.pinimg.com/1200x/87/80/58/878058896f04c77929c99fda64493ba0.jpg",
}


def supabase_config_error():
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_KEY:
        missing.append("SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY")
    if missing:
        return "Supabase is not configured. Missing: " + ", ".join(missing)
    return None


def mail_config_error():
    missing = []
    if not app.config.get('MAIL_USERNAME'):
        missing.append("MAIL_USERNAME")
    if not app.config.get('MAIL_PASSWORD'):
        missing.append("MAIL_PASSWORD")
    if not CONTACT_RECIPIENT:
        missing.append("CONTACT_RECIPIENT")
    if missing:
        return "Email is not configured. Missing: " + ", ".join(missing)
    return None


def explain_mail_error(error):
    error_text = str(error)
    lower_error = error_text.lower()
    if "email is not configured" in lower_error:
        return error_text
    if "username and password not accepted" in lower_error or "application-specific password" in lower_error:
        return "Gmail rejected the login. Use a Gmail App Password, not your normal Gmail password."
    if "authentication" in lower_error or "535" in lower_error:
        return "Gmail authentication failed. Check MAIL_USERNAME and MAIL_PASSWORD."
    if "connection" in lower_error or "timed out" in lower_error:
        return "Could not connect to Gmail SMTP. Please try again."
    return "Could not send the email right now. Please check your Gmail settings."


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
    if isinstance(error, requests.exceptions.Timeout):
        return "Supabase took too long to respond. Please try again."
    if isinstance(error, requests.exceptions.ConnectionError):
        return "Could not reach Supabase. Check your internet connection."
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    response_text = (getattr(response, "text", "") or "").lower()
    if status_code in (401, 403):
        if "row-level security" in response_text:
            return "Supabase blocked this request with Row Level Security. Check your table policies."
        return "Supabase rejected the request. Check your API key and RLS policies."
    if status_code == 404:
        return "Supabase table not found. Make sure the users, books, and bookings tables exist."
    if status_code == 409:
        return "That username already exists. Try another username."
    if status_code == 400:
        return "Supabase rejected the request. Check your table columns match the data being sent."
    if status_code and status_code >= 500:
        return "Supabase server error. Please try again in a moment."
    return "Could not connect to Supabase right now."


def build_debug_hint(error):
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    response_text = (getattr(response, "text", "") or "").strip()[:220]
    error_name = type(error).__name__
    if status_code and response_text:
        return f"{error_name} ({status_code}): {response_text}"
    if status_code:
        return f"{error_name} ({status_code})"
    return f"{error_name}: {str(error)[:220]}"


def normalize_title(title):
    return (title or "").strip().lower()


def apply_book_image(book):
    if not book:
        return book
    hydrated_book = dict(book)
    if not (hydrated_book.get("image_url") or "").strip():
        hydrated_book["image_url"] = DEFAULT_BOOK_IMAGES.get(normalize_title(hydrated_book.get("title")))
    return hydrated_book


def apply_book_images(books):
    return [apply_book_image(book) for book in books]


def db_get(table, params=None):
    config_error = supabase_config_error()
    if config_error:
        raise RuntimeError(config_error)
    try:
        p = {'select': '*'}
        if params:
            p.update(params)
        r = HTTP.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=HEADERS, params=p, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        print("db_get error:", e)
        raise


def db_post(table, data):
    config_error = supabase_config_error()
    if config_error:
        raise RuntimeError(config_error)
    try:
        h = {**HEADERS, "Prefer": "return=representation"}
        r = HTTP.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=h, json=data, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("db_post error:", e)
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
        print("db_patch error:", e)
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


# ── OTP HELPERS ───────────────────────────────────────────

def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_email(to_email, otp):
    msg = Message('Your LibraSpace Verification Code', recipients=[to_email])
    msg.body = f'Your OTP code is: {otp}\n\nThis code expires in 5 minutes.'
    mail.send(msg)


def send_contact_email(name, sender_email, subject, message_body):
    config_error = mail_config_error()
    if config_error:
        raise RuntimeError(config_error)
    msg = Message(
        subject=f"LibraSpace Contact: {subject}",
        recipients=[CONTACT_RECIPIENT],
        reply_to=sender_email
    )
    msg.body = (
        "New contact form message\n\n"
        f"Name: {name}\n"
        f"Email: {sender_email}\n"
        f"Subject: {subject}\n\n"
        f"Message:\n{message_body}"
    )
    mail.send(msg)


def save_contact_message(name, email, subject, message_body):
    try:
        db_post('contact_messages', {
            'name': name, 'email': email,
            'subject': subject, 'message': message_body,
            'is_read': False
        })
    except Exception as e:
        print('save_contact_message error:', e)


@app.route('/send-otp', methods=['POST'])
def send_otp():
    from flask import jsonify
    email = (request.get_json() or {}).get('email', '').strip()
    if not email:
        return jsonify({'success': False, 'error': 'Email is required.'})
    otp = generate_otp()
    session['otp'] = otp
    session['otp_email'] = email
    session['otp_expires'] = time.time() + 300  # 5 minutes
    try:
        send_otp_email(email, otp)
        return jsonify({'success': True})
    except Exception as e:
        print('OTP send error:', e)
        return jsonify({'success': False, 'error': 'Failed to send email.'})


@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'POST':
        entered = request.form.get('otp', '').strip()
        stored  = session.get('otp')
        expires = session.get('otp_expires', 0)
        if not stored:
            return render_template('verify_otp.html', error='No OTP requested.')
        if time.time() > expires:
            session.pop('otp', None)
            return render_template('verify_otp.html', error='OTP expired. Please request a new one.')
        if entered != stored:
            return render_template('verify_otp.html', error='Incorrect OTP. Try again.')
        session.pop('otp', None)
        session.pop('otp_expires', None)
        # complete registration if pending
        pending = session.pop('pending_register', None)
        if pending:
            try:
                db_post('users', pending)
                session['register_success'] = 'Account created! You can now log in.'
                return redirect('/login')
            except Exception as e:
                return render_template('verify_otp.html', error=explain_supabase_error(e))
        session['email_verified'] = True
        return redirect('/dashboard')
    return render_template('verify_otp.html', error=None)


# ── PUBLIC ROUTES ──────────────────────────────────────────

@app.route('/')
def home():
    try:
        books = apply_book_images(db_get('books'))
    except Exception:
        books = []
    return render_template('index.html', active_page='home', featured_books=books[:6])

@app.route('/features')
def features():
    return render_template('features.html', active_page='features')

@app.route('/about')
def about():
    return render_template('about.html', active_page='about')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        form = {
            'name': request.form.get('name', '').strip(),
            'email': request.form.get('email', '').strip(),
            'subject': request.form.get('subject', 'General Inquiry').strip(),
            'message': request.form.get('message', '').strip(),
        }
        if not form['name'] or not form['email'] or len(form['message']) < 10:
            return render_template(
                'contact.html',
                active_page='contact',
                sent=False,
                error='Please fill in your name, email, and a message with at least 10 characters.',
                form=form
            )
        # Always save to DB
        save_contact_message(form['name'], form['email'], form['subject'], form['message'])
        # Try to send email (non-blocking)
        try:
            send_contact_email(form['name'], form['email'], form['subject'], form['message'])
        except Exception as e:
            print('Contact mail error (non-fatal):', e)
        return render_template('contact.html', active_page='contact', sent=True, error=None, form={})
    return render_template('contact.html', active_page='contact', sent=False, error=None, form={})

@app.route('/favicon.png')
def favicon():
    return Response(status=204)


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        if new_password != confirm_password:
            return render_template('forgot_password.html', step=2, username=username, error='Passwords do not match.')
        if len(new_password) < 6:
            return render_template('forgot_password.html', step=2, username=username, error='Password must be at least 6 characters.')
        users = db_get('users', {'username': f'eq.{username}'})
        if not users:
            return render_template('forgot_password.html', step=2, username=username, error='Account not found.')
        db_patch('users', {'password': generate_password_hash(new_password)}, {'id': f"eq.{users[0]['id']}"})
        return render_template('forgot_password.html', step=3)
    return render_template('forgot_password.html', step=1)


@app.route('/verify-username', methods=['POST'])
def verify_username():
    from flask import jsonify
    data = request.get_json()
    username = (data or {}).get('username', '').strip()
    users = db_get('users', {'username': f'eq.{username}'})
    return jsonify({'found': bool(users)})


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone', '').strip()
            password = request.form.get('password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()

            if not username or not email or not phone or not password or not confirm_password:
                return render_template('register.html', **auth_page_context(error='All fields are required.'))
            if password != confirm_password:
                return render_template('register.html', **auth_page_context(error='Passwords do not match.'))
            if len(password) < 6:
                return render_template('register.html', **auth_page_context(error='Password must be at least 6 characters.'))

            # store pending registration and send OTP
            session['pending_register'] = {
                'username': username, 'email': email,
                'phone': phone, 'password': generate_password_hash(password)
            }
            otp = generate_otp()
            session['otp'] = otp
            session['otp_email'] = email
            session['otp_expires'] = time.time() + 300
            try:
                send_otp_email(email, otp)
            except Exception as mail_err:
                print('Mail error:', mail_err)
                return render_template('register.html', **auth_page_context(error=f'Failed to send OTP email: {mail_err}'))
            return redirect('/verify-otp')
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
            if not users:
                return render_template('login.html', **auth_page_context(error='No account found with that username.'))
            stored = users[0].get('password', '')
            # support both hashed and legacy plain-text passwords
            if stored.startswith(('pbkdf2:', 'scrypt:')):
                matched = check_password_hash(stored, password)
            else:
                matched = (stored == password)
                if matched:
                    # upgrade to hashed
                    db_patch('users', {'password': generate_password_hash(password)}, {'id': f"eq.{users[0]['id']}"})
            if matched:
                session['user_id'] = users[0]['id']
                session.modified = True
                return redirect('/dashboard')
            return render_template('login.html', **auth_page_context(error='Incorrect password.'))
        except Exception as e:
            print("Login error:", str(e))
            return render_template('login.html', **auth_page_context(error=explain_supabase_error(e), debug_hint=build_debug_hint(e)))
    success = session.pop('register_success', None)
    return render_template('login.html', **auth_page_context(success=success))


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['is_admin'] = True
            session['admin_username'] = username
            session.modified = True
            return redirect('/admin/dashboard')
        return render_template('admin_login.html', error='Invalid admin credentials.')
    return render_template('admin_login.html', error=None)


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    session.pop('admin_username', None)
    return redirect('/admin/login')


# ── ADMIN ─────────────────────────────────────────────────

def admin_required():
    if not session.get('is_admin'):
        return redirect('/admin/login')
    return None


@app.route('/admin/orders')
def admin_orders():
    redir = admin_required()
    if redir: return redir
    username = session.get('admin_username', 'Admin')
    try:
        all_orders = db_get('orders')
        ordered_books = []
        for order in sorted(all_orders, key=lambda x: x.get('created_at',''), reverse=True):
            try:
                book = apply_book_images(db_get('books', {'id': f"eq.{order['book_id']}"}))
                u = db_get('users', {'id': f"eq.{order['user_id']}"})
                if book:
                    entry = dict(book[0])
                    entry['order_id'] = order['id']
                    entry['ordered_at'] = order.get('created_at', '')
                    entry['status'] = order.get('status', 'pending')
                    entry['buyer'] = u[0]['username'] if u else 'Unknown'
                    ordered_books.append(entry)
            except Exception as e:
                print('Admin orders row error:', e)
    except Exception as e:
        print('Admin orders error:', e)
        ordered_books = []
    return render_template('admin_orders.html', ordered_books=ordered_books, username=username)


@app.route('/admin/dashboard')
def admin_dashboard():
    redir = admin_required()
    if redir: return redir
    username = session.get('admin_username', 'Admin')
    try:
        all_books   = db_get('books')
        all_orders  = db_get('orders')
        all_users   = db_get('users')
        pending_orders   = [o for o in all_orders if o.get('status','pending') == 'pending']
        shipped_orders   = [o for o in all_orders if o.get('status') == 'shipped']
        delivered_orders = [o for o in all_orders if o.get('status') == 'delivered']
        cancelled_orders = [o for o in all_orders if o.get('status') == 'cancelled']
        out_of_stock = [b for b in all_books if (b.get('stock') or 0) == 0]
        low_stock    = [b for b in all_books if 0 < (b.get('stock') or 0) <= 3]
        # recent orders with book info
        recent_orders = []
        for o in sorted(all_orders, key=lambda x: x.get('created_at',''), reverse=True)[:8]:
            book = db_get('books', {'id': f"eq.{o['book_id']}"})
            u    = db_get('users', {'id': f"eq.{o['user_id']}"})
            recent_orders.append({
                'id': o['id'],
                'status': o.get('status','pending'),
                'created_at': o.get('created_at',''),
                'book_title': book[0]['title'] if book else 'Unknown',
                'username': u[0]['username'] if u else 'Unknown',
                'price': book[0].get('price', 0) if book else 0,
            })
        total_revenue = sum(float(o.get('price',0)) for o in recent_orders if o['status'] != 'cancelled')
        # all orders revenue
        full_revenue = 0
        for o in all_orders:
            if o.get('status','pending') != 'cancelled':
                b = db_get('books', {'id': f"eq.{o['book_id']}"})
                if b: full_revenue += float(b[0].get('price',0) or 0)
    except Exception as e:
        print('Admin dashboard error:', e)
        all_books=all_orders=all_users=[]
        pending_orders=shipped_orders=delivered_orders=cancelled_orders=[]
        out_of_stock=low_stock=recent_orders=[]
        full_revenue=0
    return render_template('admin_dashboard.html',
        username=username,
        total_books=len(all_books),
        total_orders=len(all_orders),
        total_users=len(all_users),
        pending_orders=len(pending_orders),
        shipped_orders=len(shipped_orders),
        delivered_orders=len(delivered_orders),
        cancelled_orders=len(cancelled_orders),
        out_of_stock=len(out_of_stock),
        low_stock=len(low_stock),
        recent_orders=recent_orders,
        full_revenue=full_revenue,
    )


@app.route('/admin')
def admin():
    redir = admin_required()
    if redir: return redir
    books = apply_book_images(db_get('books'))
    username = session.get('admin_username', 'Admin')
    return render_template('admin.html', books=books, username=username)


@app.route('/admin/book/add', methods=['GET', 'POST'])
def admin_book_add():
    redir = admin_required()
    if redir: return redir
    username = session.get('admin_username', 'Admin')
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        author = request.form.get('author', '').strip()
        genre = request.form.get('genre', '').strip()
        price = request.form.get('price', '').strip()
        stock = request.form.get('stock', '0').strip()
        image_url = request.form.get('image_url', '').strip()
        description = request.form.get('description', '').strip()
        if not title or not price:
            return render_template('admin.html', books=apply_book_images(db_get('books')),
                username=username, form_error='Title and price are required.', show_add=True,
                form={'title': title, 'author': author, 'genre': genre, 'price': price, 'stock': stock, 'image_url': image_url, 'description': description})
        try:
            db_post('books', {'title': title, 'author': author, 'genre': genre,
                'price': float(price), 'stock': int(stock), 'image_url': image_url or None, 'description': description or None})
            return redirect('/admin')
        except Exception as e:
            return render_template('admin.html', books=apply_book_images(db_get('books')),
                username=username, form_error=str(e), show_add=True)
    return render_template('admin.html', books=apply_book_images(db_get('books')),
        username=username, show_add=True)


@app.route('/admin/book/<int:book_id>/edit', methods=['GET', 'POST'])
def admin_book_edit(book_id):
    redir = admin_required()
    if redir: return redir
    username = session.get('admin_username', 'Admin')
    book_result = apply_book_images(db_get('books', {'id': f'eq.{book_id}'}))
    if not book_result:
        return redirect('/admin')
    book = book_result[0]
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        author = request.form.get('author', '').strip()
        genre = request.form.get('genre', '').strip()
        price = request.form.get('price', '').strip()
        stock = request.form.get('stock', '0').strip()
        image_url = request.form.get('image_url', '').strip()
        description = request.form.get('description', '').strip()
        if not title or not price:
            return render_template('admin.html', books=apply_book_images(db_get('books')),
                username=username, form_error='Title and price are required.', edit_book=book)
        try:
            db_patch('books', {'title': title, 'author': author, 'genre': genre,
                'price': float(price), 'stock': int(stock), 'image_url': image_url or None, 'description': description or None},
                {'id': f'eq.{book_id}'})
            return redirect('/admin')
        except Exception as e:
            return render_template('admin.html', books=apply_book_images(db_get('books')),
                username=username, form_error=str(e), edit_book=book)
    return render_template('admin.html', books=apply_book_images(db_get('books')),
        username=username, edit_book=book)


@app.route('/admin/book/<int:book_id>/delete', methods=['POST'])
def admin_book_delete(book_id):
    redir = admin_required()
    if redir: return redir
    try:
        HTTP.delete(f"{SUPABASE_URL}/rest/v1/books", headers=HEADERS,
            params={'id': f'eq.{book_id}'}, timeout=15)
    except Exception as e:
        print('Delete book error:', e)
    return redirect('/admin')



@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    try:
        genre_filter = request.args.get('genre', '').strip()
        search_query = request.args.get('search', '').strip()
        page = max(1, int(request.args.get('page', 1)))
        per_page = 12
        offset = (page - 1) * per_page

        params = {'limit': per_page, 'offset': offset}
        if genre_filter:
            params['genre'] = f'eq.{genre_filter}'
        if search_query:
            params['or'] = f'(title.ilike.*{search_query}*,author.ilike.*{search_query}*,description.ilike.*{search_query}*)'

        books = apply_book_images(db_get('books', params))

        # total count for pagination
        count_params = {}
        if genre_filter:
            count_params['genre'] = f'eq.{genre_filter}'
        if search_query:
            count_params['or'] = f'(title.ilike.*{search_query}*,author.ilike.*{search_query}*,description.ilike.*{search_query}*)'
        total = len(db_get('books', count_params if count_params else None))
        total_pages = max(1, -(-total // per_page))  # ceiling division

        all_books = apply_book_images(db_get('books'))
        genres = sorted(set(b.get('genre', 'General') for b in all_books if b.get('genre')))
        user = db_get('users', {'id': f"eq.{session['user_id']}"})
        username = user[0]['username'] if user else 'Reader'
        cart_ids = get_cart_ids(session['user_id'])
        cart_count = len(cart_ids)
        cart_items = []
        for bid in cart_ids:
            r = apply_book_images(db_get('books', {'id': f'eq.{bid}'}))
            if r:
                cart_items.append(r[0])

        return render_template('dashboard.html', books=books, genres=genres,
            selected_genre=genre_filter, username=username, search_query=search_query,
            cart_count=cart_count, cart_items=cart_items,
            page=page, total_pages=total_pages, total=total,
            active_page='dashboard')
    except Exception as e:
        print("Dashboard error:", str(e))
        return redirect('/login')


# ── BOOK DETAIL ────────────────────────────────────────────

@app.route('/book/<int:book_id>')
def book_detail(book_id):
    if 'user_id' not in session:
        return redirect('/login')
    result = apply_book_images(db_get('books', {'id': f'eq.{book_id}'}))
    if not result:
        return redirect('/dashboard')
    user = db_get('users', {'id': f"eq.{session['user_id']}"})
    username = user[0]['username'] if user else 'Reader'
    try:
        already_owned = bool(db_get('orders', {'user_id': f"eq.{session['user_id']}", 'book_id': f'eq.{book_id}'}))
    except Exception:
        already_owned = False
    try:
        already_reserved = bool(db_get('bookings', {'user_id': f"eq.{session['user_id']}", 'book_id': f'eq.{book_id}'}))
    except Exception:
        already_reserved = False
    return render_template('book_detail.html', book=result[0], username=username,
        already_owned=already_owned, already_reserved=already_reserved)


# ── RESERVATIONS ───────────────────────────────────────────

@app.route('/reserve/<int:book_id>')
def reserve(book_id):
    if 'user_id' not in session:
        return redirect('/login')
    try:
        already_ordered = db_get('orders', {'user_id': f"eq.{session['user_id']}", 'book_id': f'eq.{book_id}'})
    except Exception:
        already_ordered = []
    if already_ordered:
        return redirect(f'/book/{book_id}?already_owned=1')
    existing = db_get('bookings', {'user_id': f"eq.{session['user_id']}", 'book_id': f'eq.{book_id}'})
    if not existing:
        db_post('bookings', {'user_id': session['user_id'], 'book_id': book_id})
    return redirect('/reservations')


@app.route('/reservations')
def reservations():
    if 'user_id' not in session:
        return redirect('/login')
    try:
        user = db_get('users', {'id': f"eq.{session['user_id']}"})
        username = user[0]['username'] if user else 'Reader'
        bookings = db_get('bookings', {'user_id': f"eq.{session['user_id']}"})
        reserved_books = []
        for booking in bookings:
            book_result = apply_book_images(db_get('books', {'id': f"eq.{booking['book_id']}"}))
            if book_result:
                entry = dict(book_result[0])
                entry['booking_id'] = booking['id']
                entry['reserved_at'] = booking.get('created_at', '')
                reserved_books.append(entry)
        cart_count = len(get_cart_ids(session['user_id']))
        return render_template('reservations.html', reserved_books=reserved_books, username=username, cart_count=cart_count)
    except Exception as e:
        print("Reservations error:", str(e))
        return redirect('/dashboard')


@app.route('/cancel/<int:booking_id>')
def cancel(booking_id):
    if 'user_id' not in session:
        return redirect('/login')
    try:
        HTTP.delete(
            f"{SUPABASE_URL}/rest/v1/bookings",
            headers=HEADERS,
            params={'id': f'eq.{booking_id}', 'user_id': f"eq.{session['user_id']}"},
            timeout=15
        )
    except Exception as e:
        print("Cancel error:", str(e))
    return redirect('/reservations')


# ── PROFILE ────────────────────────────────────────────────

def profile_render(**kwargs):
    user = db_get('users', {'id': f"eq.{session['user_id']}"})
    username = user[0]['username'] if user else 'Reader'
    email = user[0].get('email', '') if user else ''
    phone = user[0].get('phone', '') if user else ''
    try:
        orders = db_get('orders', {'user_id': f"eq.{session['user_id']}"})
        orders_count = len(orders)
    except Exception:
        orders_count = 0
    try:
        genres = sorted(set(b.get('genre') for b in apply_book_images(db_get('books')) if b.get('genre')))
    except Exception:
        genres = []
    ctx = dict(username=username, email=email, phone=phone, orders_count=orders_count,
        username_error=None, username_success=None,
        password_error=None, password_success=None,
        contact_error=None, contact_success=None,
        genres=genres, selected_genre=None)
    ctx.update(kwargs)
    return render_template('profile.html', **ctx)


@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect('/login')
    try:
        return profile_render()
    except Exception as e:
        print("Profile error:", str(e))
        return redirect('/dashboard')


@app.route('/profile/username', methods=['POST'])
def profile_username():
    if 'user_id' not in session:
        return redirect('/login')
    try:
        new_username = request.form.get('new_username', '').strip()
        if not new_username or len(new_username) < 3:
            return profile_render(username_error='Username must be at least 3 characters.')
        existing = db_get('users', {'username': f'eq.{new_username}'})
        if existing and existing[0]['id'] != session['user_id']:
            return profile_render(username_error='That username is already taken.')
        result = db_patch('users', {'username': new_username}, {'id': f"eq.{session['user_id']}"})
        if not result:
            return profile_render(username_error='Update failed. This may be blocked by a database policy. Please contact support.')
        return profile_render(username_success='Username updated successfully!')
    except Exception as e:
        print("Profile username error:", str(e))
        return profile_render(username_error=explain_supabase_error(e))


@app.route('/profile/password', methods=['POST'])
def profile_password():
    if 'user_id' not in session:
        return redirect('/login')
    try:
        current_password = request.form.get('current_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        user = db_get('users', {'id': f"eq.{session['user_id']}"})
        if not user or not password_matches(user[0].get('password'), current_password):
            return profile_render(password_error='Current password is incorrect.')
        if new_password != confirm_password:
            return profile_render(password_error='New passwords do not match.')
        if len(new_password) < 6:
            return profile_render(password_error='Password must be at least 6 characters.')
        db_patch('users', {'password': generate_password_hash(new_password)}, {'id': f"eq.{session['user_id']}"})
        return profile_render(password_success='Password updated successfully!')
    except Exception as e:
        print("Profile password error:", str(e))
        return profile_render(password_error='Something went wrong. Please try again.')


@app.route('/profile/contact', methods=['POST'])
def profile_contact():
    if 'user_id' not in session:
        return redirect('/login')
    try:
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        if not email or not phone:
            return profile_render(contact_error='Email and phone are required.')
        db_patch('users', {'email': email, 'phone': phone}, {'id': f"eq.{session['user_id']}"})
        return profile_render(contact_success='Contact info updated successfully!')
    except Exception as e:
        print("Profile contact error:", str(e))
        return profile_render(contact_error='Something went wrong. Please try again.')


def get_cart_ids(user_id):
    try:
        rows = db_get('cart', {'user_id': f'eq.{user_id}'})
        return [r['book_id'] for r in rows]
    except Exception:
        return []


def set_cart_add(user_id, book_id):
    existing = db_get('cart', {'user_id': f'eq.{user_id}', 'book_id': f'eq.{book_id}'})
    if not existing:
        db_post('cart', {'user_id': user_id, 'book_id': book_id})


def set_cart_remove(user_id, book_id):
    HTTP.delete(f"{SUPABASE_URL}/rest/v1/cart", headers=HEADERS,
        params={'user_id': f'eq.{user_id}', 'book_id': f'eq.{book_id}'}, timeout=15)


def clear_cart(user_id):
    HTTP.delete(f"{SUPABASE_URL}/rest/v1/cart", headers=HEADERS,
        params={'user_id': f'eq.{user_id}'}, timeout=15)


# ── CART ───────────────────────────────────────────────────

@app.route('/cart')
def cart():
    if 'user_id' not in session:
        return redirect('/login')
    cart_ids = get_cart_ids(session['user_id'])
    cart_books = []
    total = 0
    for book_id in cart_ids:
        result = apply_book_images(db_get('books', {'id': f'eq.{book_id}'}))
        if result:
            cart_books.append(result[0])
            total += float(result[0].get('price') or 0)
    user = db_get('users', {'id': f"eq.{session['user_id']}"})
    username = user[0]['username'] if user else 'Reader'
    genres = sorted(set(b.get('genre') for b in apply_book_images(db_get('books')) if b.get('genre')))
    return render_template('cart.html', cart_books=cart_books, total=round(total, 2), username=username, cart_count=len(cart_ids), genres=genres, selected_genre=None)


@app.route('/cart/add/<int:book_id>')
def cart_add(book_id):
    if 'user_id' not in session:
        return redirect('/login')
    set_cart_add(session['user_id'], book_id)
    return redirect('/cart')


@app.route('/cart/remove/<int:book_id>')
def cart_remove(book_id):
    if 'user_id' not in session:
        return redirect('/login')
    set_cart_remove(session['user_id'], book_id)
    return redirect('/cart')


@app.route('/cart/checkout', methods=['GET'])
def cart_checkout():
    if 'user_id' not in session:
        return redirect('/login')
    cart_ids = get_cart_ids(session['user_id'])
    if not cart_ids:
        return redirect('/cart')
    cart_books = []
    for bid in cart_ids:
        r = apply_book_images(db_get('books', {'id': f'eq.{bid}'}))
        if r:
            cart_books.append(r[0])
    user = db_get('users', {'id': f"eq.{session['user_id']}"})
    username = user[0]['username'] if user else 'Reader'
    total = round(sum(float(b.get('price') or 0) for b in cart_books), 2)
    return render_template('cart_checkout.html', cart_books=cart_books, total=total,
        username=username, error=None, form=None)


@app.route('/cart/checkout/place', methods=['POST'])
def cart_checkout_place():
    if 'user_id' not in session:
        return redirect('/login')
    street = request.form.get('street', '').strip()
    location = request.form.get('location', '').strip()
    payment = request.form.get('payment', '').strip()
    cart_ids = get_cart_ids(session['user_id'])
    if not cart_ids:
        return redirect('/cart')
    cart_books = []
    for bid in cart_ids:
        r = apply_book_images(db_get('books', {'id': f'eq.{bid}'}))
        if r:
            cart_books.append(r[0])
    user = db_get('users', {'id': f"eq.{session['user_id']}"})
    username = user[0]['username'] if user else 'Reader'
    if not street or not location or payment not in ('COD', 'GCash'):
        total = round(sum(float(b.get('price') or 0) for b in cart_books), 2)
        return render_template('cart_checkout.html', cart_books=cart_books, total=total,
            username=username, error='Please fill in all delivery details and select a payment method.',
            form={'street': street, 'location': location, 'payment': payment})
    for book_id in cart_ids:
        try:
            book = db_get('books', {'id': f'eq.{book_id}'})
            if not book or int(book[0].get('stock') or 0) <= 0:
                continue
            already = db_get('orders', {'user_id': f"eq.{session['user_id']}", 'book_id': f'eq.{book_id}'})
            if already:
                continue
            db_post('orders', {'user_id': session['user_id'], 'book_id': book_id})
            db_patch('books', {'stock': int(book[0]['stock']) - 1}, {'id': f'eq.{book_id}'})
        except Exception as e:
            print('Cart place error:', e)
    clear_cart(session['user_id'])
    return redirect('/orders?checkout=1')


# ── BUY ────────────────────────────────────────────────────

@app.route('/buy/<int:book_id>')
def buy(book_id):
    if 'user_id' not in session:
        return redirect('/login')
    try:
        existing_order = db_get('orders', {'user_id': f"eq.{session['user_id']}", 'book_id': f'eq.{book_id}'})
    except Exception:
        existing_order = []
    if existing_order:
        return redirect(f'/book/{book_id}?already_owned=1')
    book_result = apply_book_images(db_get('books', {'id': f'eq.{book_id}'}))
    if not book_result or int(book_result[0].get('stock') or 0) <= 0:
        return redirect(f'/book/{book_id}?out_of_stock=1')
    user = db_get('users', {'id': f"eq.{session['user_id']}"})
    username = user[0]['username'] if user else 'Reader'
    return render_template('checkout.html', book=book_result[0], username=username, error=None, form=None)


@app.route('/buy/<int:book_id>/place', methods=['POST'])
def buy_place(book_id):
    if 'user_id' not in session:
        return redirect('/login')
    street = request.form.get('street', '').strip()
    location = request.form.get('location', '').strip()
    payment = request.form.get('payment', '').strip()
    book_result = apply_book_images(db_get('books', {'id': f'eq.{book_id}'}))
    if not street or not location or payment not in ('COD', 'GCash'):
        user = db_get('users', {'id': f"eq.{session['user_id']}"})
        username = user[0]['username'] if user else 'Reader'
        return render_template('checkout.html', book=book_result[0] if book_result else {}, username=username,
            error='Please fill in all delivery details and select a payment method.',
            form={'street': street, 'location': location, 'payment': payment})
    if not book_result or int(book_result[0].get('stock') or 0) <= 0:
        return redirect(f'/book/{book_id}?out_of_stock=1')
    try:
        existing_order = db_get('orders', {'user_id': f"eq.{session['user_id']}", 'book_id': f'eq.{book_id}'})
    except Exception:
        existing_order = []
    if existing_order:
        return redirect(f'/book/{book_id}?already_owned=1')
    book = db_get('books', {'id': f'eq.{book_id}'})
    if not book or int(book[0].get('stock') or 0) <= 0:
        return redirect(f'/book/{book_id}?out_of_stock=1')
    try:
        db_post('orders', {'user_id': session['user_id'], 'book_id': book_id})
        db_patch('books', {'stock': int(book[0]['stock']) - 1}, {'id': f'eq.{book_id}'})
        existing_booking = db_get('bookings', {'user_id': f"eq.{session['user_id']}", 'book_id': f'eq.{book_id}'})
        if existing_booking:
            HTTP.delete(f"{SUPABASE_URL}/rest/v1/bookings", headers=HEADERS,
                params={'id': f"eq.{existing_booking[0]['id']}", 'user_id': f"eq.{session['user_id']}"}, timeout=15)
    except Exception as e:
        print('Buy place error:', e)
        return redirect(f'/book/{book_id}?error=1')
    return redirect('/orders?checkout=1')


# ── ORDERS ──────────────────────────────────────────────────

@app.route('/orders/statuses')
def orders_statuses():
    from flask import jsonify
    if 'user_id' not in session:
        return jsonify([])
    try:
        order_rows = db_get('orders', {'user_id': f"eq.{session['user_id']}"})
        result = []
        for o in order_rows:
            book = db_get('books', {'id': f"eq.{o['book_id']}"})
            result.append({'id': o['id'], 'status': o.get('status', 'pending'), 'title': book[0]['title'] if book else 'Unknown'})
        return jsonify(result)
    except Exception:
        return jsonify([])


@app.route('/orders')
def orders():
    if 'user_id' not in session:
        return redirect('/login')
    try:
        user = db_get('users', {'id': f"eq.{session['user_id']}"})
        username = user[0]['username'] if user else 'Reader'
        order_rows = db_get('orders', {'user_id': f"eq.{session['user_id']}"})
        ordered_books = []
        for order in order_rows:
            try:
                result = apply_book_images(db_get('books', {'id': f"eq.{order['book_id']}"}))
                if result:
                    entry = dict(result[0])
                    entry['order_id'] = order['id']
                    entry['ordered_at'] = order.get('created_at', '')
                    entry['status'] = order.get('status', 'pending')
                    ordered_books.append(entry)
            except Exception as e:
                print('Orders row error:', e)
        cart_count = len(get_cart_ids(session['user_id']))
        genres = sorted(set(b.get('genre') for b in apply_book_images(db_get('books')) if b.get('genre')))
        return render_template('orders.html', ordered_books=ordered_books, username=username, cart_count=cart_count, genres=genres, selected_genre=None)
    except Exception as e:
        print('Orders error:', e)
        return render_template('orders.html', ordered_books=[], username='Reader', cart_count=0, genres=[], selected_genre=None)


@app.route('/order/cancel/<int:order_id>')
def order_cancel(order_id):
    if 'user_id' not in session:
        return redirect('/login')
    try:
        order = db_get('orders', {'id': f'eq.{order_id}', 'user_id': f"eq.{session['user_id']}"})
        if order and order[0].get('status', 'pending') == 'pending':
            db_patch('orders', {'status': 'cancelled'}, {'id': f'eq.{order_id}', 'user_id': f"eq.{session['user_id']}"})
    except Exception as e:
        print('Order cancel error:', e)
    return redirect('/orders')


@app.route('/admin/users')
def admin_users():
    redir = admin_required()
    if redir: return redir
    username = session.get('admin_username', 'Admin')
    try:
        all_users = db_get('users')
        all_orders = db_get('orders')
        users = []
        for u in all_users:
            order_count = len([o for o in all_orders if o.get('user_id') == u.get('id')])
            users.append({
                'id': u.get('id'),
                'username': u.get('username'),
                'email': u.get('email'),
                'phone': u.get('phone'),
                'created_at': u.get('created_at', ''),
                'order_count': order_count,
                'status': 'Active' if order_count > 0 else 'Inactive',
            })
    except Exception:
        users = []
    return render_template('admin_users.html', users=users, username=username)


@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
def admin_delete_user(user_id):
    redir = admin_required()
    if redir: return redir
    try:
        HTTP.delete(f"{SUPABASE_URL}/rest/v1/users", headers=HEADERS, params={'id': f'eq.{user_id}'}, timeout=15)
    except Exception as e:
        print('Admin delete user error:', e)
    return redirect('/admin/users')


@app.route('/admin/user/<int:user_id>/orders')
def admin_user_orders(user_id):
    redir = admin_required()
    if redir: return redir
    username = session.get('admin_username', 'Admin')
    try:
        u = db_get('users', {'id': f'eq.{user_id}'})
        user_info = u[0] if u else {}
        order_rows = db_get('orders', {'user_id': f'eq.{user_id}'})
        ordered_books = []
        for order in order_rows:
            book = apply_book_images(db_get('books', {'id': f"eq.{order['book_id']}"}))
            if book:
                entry = dict(book[0])
                entry['order_id'] = order['id']
                entry['ordered_at'] = order.get('created_at', '')
                entry['status'] = order.get('status', 'pending')
                ordered_books.append(entry)
    except Exception:
        ordered_books = []
        user_info = {}
    return render_template('admin_user_orders.html', ordered_books=ordered_books, user_info=user_info, username=username)


@app.route('/admin/reservations')
def admin_reservations():
    redir = admin_required()
    if redir: return redir
    username = session.get('admin_username', 'Admin')
    try:
        all_bookings = db_get('bookings')
        reservations = []
        for b in sorted(all_bookings, key=lambda x: x.get('created_at', ''), reverse=True):
            book = db_get('books', {'id': f"eq.{b['book_id']}"})
            u    = db_get('users', {'id': f"eq.{b['user_id']}"})
            reservations.append({
                'id': b['id'],
                'book_title': book[0]['title'] if book else 'Unknown',
                'username': u[0]['username'] if u else 'Unknown',
                'created_at': b.get('created_at', ''),
            })
    except Exception:
        reservations = []
    return render_template('admin_reservations.html', reservations=reservations, username=username)


@app.route('/admin/reservation/<int:booking_id>/cancel', methods=['POST'])
def admin_cancel_reservation(booking_id):
    redir = admin_required()
    if redir: return redir
    try:
        HTTP.delete(f"{SUPABASE_URL}/rest/v1/bookings", headers=HEADERS,
            params={'id': f'eq.{booking_id}'}, timeout=15)
    except Exception as e:
        print('Admin cancel reservation error:', e)
    return redirect('/admin/reservations')


@app.route('/admin/orders/pending-count')
def admin_pending_count():
    from flask import jsonify
    redir = admin_required()
    if redir: return jsonify({'count': 0})
    try:
        orders = db_get('orders', {'status': 'eq.pending'})
        return jsonify({'count': len(orders)})
    except Exception:
        return jsonify({'count': 0})


@app.route('/admin/contact-messages/unread-count')
def admin_contact_unread_count():
    from flask import jsonify
    redir = admin_required()
    if redir: return jsonify({'count': 0})
    try:
        msgs = db_get('contact_messages', {'is_read': 'eq.false'})
        return jsonify({'count': len(msgs)})
    except Exception:
        return jsonify({'count': 0})


@app.route('/admin/contact-messages')
def admin_contact_messages():
    redir = admin_required()
    if redir: return redir
    username = session.get('admin_username', 'Admin')
    try:
        messages = sorted(
            db_get('contact_messages'),
            key=lambda x: x.get('created_at', ''), reverse=True
        )
    except Exception:
        messages = []
    return render_template('admin_contact_messages.html', messages=messages, username=username)


@app.route('/admin/contact-messages/<int:msg_id>/read', methods=['POST'])
def admin_contact_mark_read(msg_id):
    redir = admin_required()
    if redir: return redir
    try:
        db_patch('contact_messages', {'is_read': True}, {'id': f'eq.{msg_id}'})
    except Exception as e:
        print('mark read error:', e)
    return redirect('/admin/contact-messages')


@app.route('/admin/order/<int:order_id>/status', methods=['POST'])
def admin_order_status(order_id):
    redir = admin_required()
    if redir: return redir
    status = request.form.get('status', '').strip()
    if status in ('pending', 'shipped', 'delivered', 'cancelled'):
        db_patch('orders', {'status': status}, {'id': f'eq.{order_id}'})
    return redirect(request.referrer or '/admin')


if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true')
