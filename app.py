# app.py
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from hijri_converter import Gregorian
import json
import locale
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'daywise-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///daywise.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Set locale for date formatting
locale.setlocale(locale.LC_TIME, 'en_US.UTF-8')

# Define constants
PRIORITIES = {'low': 'Low', 'medium': 'Medium', 'high': 'High'}
TIME_BLOCKS = {'any': 'Any', 'morning': 'Morning', 'afternoon': 'Afternoon', 'evening': 'Evening'}

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    dark_mode = db.Column(db.Boolean, default=False)
    tasks = db.relationship('Task', backref='user', lazy='dynamic')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    estimated_time = db.Column(db.Integer, nullable=False)  # in minutes
    is_completed = db.Column(db.Boolean, default=False)
    priority = db.Column(db.String(20), default='medium')
    time_block = db.Column(db.String(20), default='any')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'description': self.description,
            'estimatedTime': self.estimated_time,
            'isCompleted': self.is_completed,
            'priority': self.priority,
            'timeBlock': self.time_block
        }

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Helper functions
def get_dates():
    today = datetime.now()
    gregorian_date = today.strftime("%A, %B %d, %Y")
    
    hijri_date_obj = Gregorian(today.year, today.month, today.day).to_hijri()
    
    hijri_months = ["Muharram", "Safar", "Rabi' al-Awwal", "Rabi' al-Thani", 
                    "Jumada al-Awwal", "Jumada al-Thani", "Rajab", "Sha'ban",
                    "Ramadan", "Shawwal", "Dhu al-Qi'dah", "Dhu al-Hijjah"]
    hijri_date = f"{hijri_date_obj.day} {hijri_months[hijri_date_obj.month-1]}, {hijri_date_obj.year} AH"
    
    return gregorian_date, hijri_date

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Check if passwords match
        if password != confirm_password:
            flash('Passwords do not match')
            return redirect(url_for('register'))
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
        
        new_user = User(username=username)
        new_user.set_password(password)
        
        # Add sample tasks for new users
        sample_tasks = [
            Task(description='Morning workout', estimated_time=45, is_completed=False, priority='medium', time_block='morning', user=new_user),
            Task(description='Team meeting', estimated_time=60, is_completed=False, priority='high', time_block='morning', user=new_user),
            Task(description='Work on Project X', estimated_time=120, is_completed=False, priority='high', time_block='afternoon', user=new_user),
            Task(description='Read documentation', estimated_time=30, is_completed=True, priority='low', time_block='any', user=new_user)
        ]
        
        db.session.add(new_user)
        for task in sample_tasks:
            db.session.add(task)
        db.session.commit()
        
        login_user(new_user)
        return redirect(url_for('dashboard'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    gregorian_date, hijri_date = get_dates()
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    
    # Calculate progress
    total_tasks = len(tasks)
    completed_tasks = sum(1 for task in tasks if task.is_completed)
    in_progress_tasks = total_tasks - completed_tasks
    percentage = round((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
    
    # Sort tasks
    sorted_tasks = sort_tasks(tasks)
    
    return render_template(
        'dashboard.html', 
        tasks=sorted_tasks,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        in_progress_tasks=in_progress_tasks,
        percentage=percentage,
        gregorian_date=gregorian_date,
        hijri_date=hijri_date,
        PRIORITIES=PRIORITIES,
        TIME_BLOCKS=TIME_BLOCKS,
        dark_mode=current_user.dark_mode
    )

def sort_tasks(tasks):
    priority_order = {'high': 1, 'medium': 2, 'low': 3}
    time_block_order = {'morning': 1, 'afternoon': 2, 'evening': 3, 'any': 4}
    
    def task_sort_key(task):
        # First by completion status (incomplete first)
        completion_key = 1 if task.is_completed else 0
        # Then by time block
        block_key = time_block_order.get(task.time_block, 99)
        # Then by priority
        priority_key = priority_order.get(task.priority, 99)
        # Finally alphabetically
        name_key = task.description.lower()
        
        return (completion_key, block_key, priority_key, name_key)
    
    return sorted(tasks, key=task_sort_key)

@app.route('/toggle_dark_mode', methods=['POST'])
@login_required
def toggle_dark_mode():
    current_user.dark_mode = not current_user.dark_mode
    db.session.commit()
    return jsonify({'success': True, 'dark_mode': current_user.dark_mode})

@app.route('/add_task', methods=['POST'])
@login_required
def add_task():
    description = request.form.get('description')
    estimated_time = request.form.get('estimated_time')
    priority = request.form.get('priority')
    time_block = request.form.get('time_block')
    
    if not description or not estimated_time or int(estimated_time) <= 0:
        flash('Please enter a valid task description and estimated time.')
        return redirect(url_for('dashboard'))
    
    new_task = Task(
        description=description,
        estimated_time=int(estimated_time),
        priority=priority,
        time_block=time_block,
        user_id=current_user.id
    )
    
    db.session.add(new_task)
    db.session.commit()
    
    return redirect(url_for('dashboard'))

@app.route('/toggle_task/<int:task_id>', methods=['POST'])
@login_required
def toggle_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    task.is_completed = not task.is_completed
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/edit_task/<int:task_id>', methods=['POST'])
@login_required
def edit_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    
    description = request.form.get('description')
    estimated_time = request.form.get('estimated_time')
    priority = request.form.get('priority')
    time_block = request.form.get('time_block')
    
    if not description or not estimated_time or int(estimated_time) <= 0:
        flash('Please enter a valid task description and estimated time.')
        return redirect(url_for('dashboard'))
    
    task.description = description
    task.estimated_time = int(estimated_time)
    task.priority = priority
    task.time_block = time_block
    
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/delete_task/<int:task_id>', methods=['POST'])
@login_required
def delete_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    db.session.delete(task)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/reset_all_tasks', methods=['POST'])
@login_required
def reset_all_tasks():
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    for task in tasks:
        task.is_completed = False
    db.session.commit()
    return redirect(url_for('dashboard'))

# Create the database tables
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)