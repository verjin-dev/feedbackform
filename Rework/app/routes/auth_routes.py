from flask import Blueprint, request, jsonify
from app.models.user import User, Role
from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token

auth_bp = Blueprint("auth", __name__)

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    user = User.query.filter_by(username=username).first()
    if user and check_password_hash(user.password, password):
        access_token = create_access_token(identity={"id": user.id, "role": user.role.value})
        return jsonify(access_token=access_token), 200
    return jsonify(msg="Invalid credentials"), 401

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data['username']
    password = generate_password_hash(data['password'])
    role = data['role']
    name = data.get('name', '')
    email = data.get('email', '')

    if User.query.filter_by(username=username).first():
        return jsonify(msg="Username already exists"), 400

    new_user = User(username=username, password=password, role=Role(role), name=name, email=email)
    db.session.add(new_user)
    db.session.commit()

    return jsonify(msg="User registered successfully"), 201
