# app/models/feedback.py
from app import db

class Feedback(db.Model):
    __tablename__ = 'feedback'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    faculty_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    subject = db.Column(db.String(255))
    rating = db.Column(db.Integer)  # Scale 1-5
    comments = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
