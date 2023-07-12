from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from flask_hashing import Hashing
from flask_session import Session
from celery import Celery
import time

app = Flask(__name__)

# Secret key for session management
app.config['SECRET_KEY'] = '106b178192d6a621080059bf117e4e29a3dbf915a0f0dac8'

# Configure database
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:admin@localhost/taskmanager'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure session
app.config['SESSION_TYPE'] = 'filesystem'  # Use filesystem-based sessions
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Initialize Flask extensions
db = SQLAlchemy(app)
ma = Marshmallow(app)
hashing = Hashing(app)
sess = Session(app)

# Initialize Celery
celery = Celery(app.name, broker='pyamqp://guest@localhost//')
celery.conf.update(app.config)


# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)


# Task model
class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    description = db.Column(db.Text, nullable=False)
    creation_date = db.Column(db.DateTime, default=db.func.current_timestamp())
    due_date = db.Column(db.DateTime)
    status = db.Column(db.Enum('not started', 'in progress', 'completed'), default='not started')


class TaskSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Task
        load_instance = True


task_schema = TaskSchema()
tasks_schema = TaskSchema(many=True)


@celery.task
def send_confirmation_email(email):
    # Just simulating email sending with a delay
    time.sleep(5)
    print(f'Sent confirmation email to {email}')


@app.route('/signup', methods=['POST'])
def signup():
    email = request.json.get('email')
    password = request.json.get('password')

    # Check if email is already in use
    user = User.query.filter_by(email=email).first()
    if user:
        return jsonify({'message': 'Email address already in use'}), 400

    # Hash password and create new user
    pw_hash = hashing.hash_value(password, salt='some_salt')
    new_user = User(email=email, password=pw_hash)
    db.session.add(new_user)
    db.session.commit()

    # Send confirmation email asynchronously
    send_confirmation_email.delay(email)

    return jsonify({'message': 'User created'}), 201


@app.route('/login', methods=['POST'])
def login():
    email = request.json.get('email')
    password = request.json.get('password')

    # Verify email and password
    user = User.query.filter_by(email=email).first()
    if user and hashing.check_value(user.password, password, salt='some_salt'):
        # Login successful, store user id in session
        session['user_id'] = user.id
        return jsonify({'message': 'Login successful'}), 200
    else:
        return jsonify({'message': 'Invalid email or password'}), 400


@app.route('/tasks', methods=['POST'])
def create_task():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'message': 'User not logged in'}), 401
    description = request.json.get('description')
    due_date = request.json.get('due_date')
    status = request.json.get('status', 'not started')
    new_task = Task(user_id=user_id, description=description, due_date=due_date, status=status)
    db.session.add(new_task)
    db.session.commit()
    return task_schema.jsonify(new_task), 201


@app.route('/tasks', methods=['GET'])
def get_tasks():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'message': 'User not logged in'}), 401
    tasks = Task.query.filter_by(user_id=user_id).all()
    return tasks_schema.jsonify(tasks), 200


@app.route('/tasks/<int:id>', methods=['GET'])
def get_task(id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'message': 'User not logged in'}), 401
    task = Task.query.filter_by(user_id=user_id, id=id).first()
    if task is None:
        return jsonify({'message': 'Task not found'}), 404
    return task_schema.jsonify(task), 200


@app.route('/tasks/<int:id>', methods=['PUT'])
def update_task(id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'message': 'User not logged in'}), 401
    task = Task.query.filter_by(user_id=user_id, id=id).first()
    if task is None:
        return jsonify({'message': 'Task not found'}), 404
    task.description = request.json.get('description', task.description)
    task.due_date = request.json.get('due_date', task.due_date)
    task.status = request.json.get('status', task.status)
    db.session.commit()
    return task_schema.jsonify(task), 200


@app.route('/tasks/<int:id>', methods=['DELETE'])
def delete_task(id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'message': 'User not logged in'}), 401
    task = Task.query.filter_by(user_id=user_id, id=id).first()
    if task is None:
        return jsonify({'message': 'Task not found'}), 404
    db.session.delete(task)
    db.session.commit()
    return jsonify({'message': 'Task deleted'}), 200


if __name__ == "__main__":
    app.run(debug=True)