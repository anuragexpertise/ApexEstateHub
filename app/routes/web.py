# app/routes/web.py
from flask import Blueprint, redirect, url_for

web_bp = Blueprint('web', __name__)

@web_bp.route('/')
def index():
    return redirect('/dashboard/')