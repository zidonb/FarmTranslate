import json
import os
from typing import Optional

DB_FILE = "users.json"

def load_data():
    """Load user data from JSON file"""
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, 'r') as f:
        return json.load(f)

def save_data(data):
    """Save user data to JSON file"""
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_user(user_id: str) -> Optional[dict]:
    """Get user data by ID"""
    data = load_data()
    return data.get(str(user_id))

def save_user(user_id: str, user_data: dict):
    """Save or update user data"""
    data = load_data()
    data[str(user_id)] = user_data
    save_data(data)

def get_all_users():
    """Get all users"""
    return load_data()