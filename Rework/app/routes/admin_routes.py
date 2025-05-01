from flask import Blueprint, jsonify
from app.models.user import User
from flask_jwt_extended import jwt_required, get_jwt_identity

admin_bp = Blueprint("admin", __name__)

@admin_bp.route('/users', methods=['GET'])
@jwt_required()
def list_users():
    current_user = get_jwt_identity()
    if current_user['role'] != 'admin':
        return jsonify(msg="Admin access only"), 403

    users = User.query.all()
    return jsonify([{
        "id": u.id,
        "username": u.username,
        "role": u.role.value,
        "name": u.name,
        "email": u.email
    } for u in users])
