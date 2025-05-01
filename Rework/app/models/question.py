# app/models/question.py
from app import db

class Question(db.Model):
    __tablename__ = 'questions'

    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(255), nullable=False)
    type = db.Column(db.String(50))  # e.g., rating, text
    options = db.Column(db.Text)  # JSON string for options if applicable
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    