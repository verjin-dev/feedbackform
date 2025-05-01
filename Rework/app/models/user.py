# app/models/user.py
from app import db
from sqlalchemy import Enum
import enum

class Role(enum.Enum):
    admin = "admin"
    faculty = "faculty"
    student = "student"

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)  # Hashed
    role = db.Column(db.Enum(Role), nullable=False)
    name = db.Column(db.String(150))
    email = db.Column(db.String(120), unique=True)
