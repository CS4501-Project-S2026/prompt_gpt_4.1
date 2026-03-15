import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user

# Setup
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['DATABASE'] = 'database.db'
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'svg'}

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Database helpers
def get_db():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with open('schema.sql', 'r') as f:
        conn = get_db()
        conn.executescript(f.read())
        # Insert three art prompts if not exists:
        prompts = [
            ("Art Prompt #1: Dreamscapes", "Create an imaginative scene set in a surreal dream world."),
            ("Art Prompt #2: Contrasts", "Make an artwork expressing contrast: dark/light, joy/sorrow, etc."),
            ("Art Prompt #3: Nature's Rhythm", "Capture the rhythm and flow found in nature—waves, wind, growth.")
        ]
        cur = conn.execute('SELECT COUNT(*) as count FROM prompt')
        if cur.fetchone()['count'] < 3:
            conn.executemany('INSERT INTO prompt (title, description) VALUES (?,?)', prompts)
        conn.commit()
        conn.close()

@app.before_first_request
def startup():
    init_db()

# User loader for Flask-Login
class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash

    @staticmethod
    def get(user_id):
        conn = get_db()
        cur = conn.execute('SELECT * FROM user WHERE id = ?', (user_id,))
        user = cur.fetchone()
        conn.close()
        if user:
            return User(user['id'], user['username'], user['password'])
        return None

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# Helpers
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Routes

@app.route('/')
def home():
    conn = get_db()
    prompts = conn.execute('SELECT * FROM prompt').fetchall()
    return render_template('home.html', prompts=prompts)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if not username or not password:
            flash('Username and password required.')
            return redirect(url_for('register'))
        hash_pw = generate_password_hash(password)
        conn = get_db()
        try:
            conn.execute('INSERT INTO user (username, password) VALUES (?,?)', (username, hash_pw))
            conn.commit()
            flash('Account created. Please log in.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already used.')
            return redirect(url_for('register'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        conn = get_db()
        user = conn.execute('SELECT * FROM user WHERE username=?', (username,)).fetchone()
        if user and check_password_hash(user['password'], password):
            user_obj = User(user['id'], user['username'], user['password'])
            login_user(user_obj)
            return redirect(url_for('home'))
        else:
            flash('Invalid credentials.')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.')
    return redirect(url_for('home'))

@app.route('/prompt/<int:prompt_id>', methods=['GET', 'POST'])
def prompt_page(prompt_id):
    conn = get_db()
    prompt = conn.execute('SELECT * FROM prompt WHERE id=?', (prompt_id,)).fetchone()
    if not prompt:
        abort(404)
    if request.method == 'POST':
        if not current_user.is_authenticated:
            flash('Please login to post.')
            return redirect(url_for('login'))

        text = request.form.get('text', '').strip()
        file = request.files.get('file')
        filename = None

        if file and file.filename != '':
            if allowed_file(file.filename):
                filename = secure_filename(f"{current_user.id}_{prompt_id}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            else:
                flash('Invalid file type.')
                return redirect(url_for('prompt_page', prompt_id=prompt_id))

        conn.execute(
            'INSERT INTO response (user_id, prompt_id, text, filename) VALUES (?, ?, ?, ?)',
            (current_user.id, prompt_id, text, filename)
        )
        conn.commit()
        flash('Your response has been posted!')
        return redirect(url_for('prompt_page', prompt_id=prompt_id))

    # Show responses
    responses = conn.execute(
        'SELECT response.*, user.username FROM response JOIN user ON user.id = response.user_id WHERE prompt_id=? ORDER BY timestamp ASC',
        (prompt_id,)
    ).fetchall()
    return render_template('prompt.html', prompt=prompt, responses=responses)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Error pages
@app.errorhandler(404)
def page_not_found(e):
    return render_template('base.html', title="Not found", content="<h2>404 - Not Found</h2>"), 404

# Run
if __name__ == "__main__":
    app.run(debug=True)