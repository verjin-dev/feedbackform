from flask import Blueprint, request, jsonify
from app.models.feedback import Feedback
from app import db
from flask_jwt_extended import jwt_required, get_jwt_identity

feedback_bp = Blueprint("feedback", __name__)

@feedback_bp.route('/', methods=['POST'])
@jwt_required()
def submit_feedback():
    user = get_jwt_identity()
    data = request.get_json()

    feedback = Feedback(
        student_id=user['id'],
        faculty_id=data['faculty_id'],
        subject=data['subject'],
        rating=data['rating'],
        comments=data.get('comments', '')
    )

    db.session.add(feedback)
    db.session.commit()
    return jsonify(msg="Feedback submitted successfully"), 201

@feedback_bp.route('/<int:faculty_id>', methods=['GET'])
@jwt_required()
def get_feedback(faculty_id):
    feedbacks = Feedback.query.filter_by(faculty_id=faculty_id).all()
    return jsonify([{
        "id": f.id,
        "student_id": f.student_id,
        "subject": f.subject,
        "rating": f.rating,
        "comments": f.comments,
        "created_at": f.created_at
    } for f in feedbacks])
