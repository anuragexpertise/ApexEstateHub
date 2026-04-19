from database.db_manager import db

def get_societies():
    """Get all societies"""
    try:
        query = "SELECT id, name, email, phone FROM societies ORDER BY name"
        result = db.execute_query(query, fetch_all=True)
        return result if result else []
    except Exception as e:
        print(f"Error getting societies: {e}")
        return []


def get_society_details(society_id):
    """Get society details by ID"""
    try:
        query = "SELECT * FROM societies WHERE id = %s"
        return db.execute_query(query, (society_id,), fetch_one=True)
    except Exception as e:
        print(f"Error getting society details: {e}")
        return None


def create_society(data):
    """Create a new society"""
    try:
        query = """
            INSERT INTO societies (name, email, phone, address, secretary_name, 
                                   secretary_phone, plan, plan_validity, arrear_start_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        params = (
            data.get('name'), data.get('email'), data.get('phone'),
            data.get('address'), data.get('sec_name'), data.get('sec_phone'),
            data.get('plan', 'Free'), data.get('validity'), data.get('arrear')
        )
        result = db.execute_query(query, params, fetch_one=True)
        
        if result and result.get('id'):
            society_id = result['id']
            if data.get('admin_email') and data.get('admin_password'):
                create_society_admin(society_id, data.get('admin_email'), data.get('admin_password'))
            return society_id
        return None
    except Exception as e:
        print(f"Error creating society: {e}")
        return None


def create_society_full(data):
    """Create a new society with full details"""
    return create_society(data)


def create_society_admin(society_id, email, password):
    """Create admin user for a society"""
    try:
        from werkzeug.security import generate_password_hash
        password_hash = generate_password_hash(password)
        query = """
            INSERT INTO users (society_id, email, password_hash, role, login_method)
            VALUES (%s, %s, %s, 'admin', 'password')
            RETURNING id
        """
        result = db.execute_query(query, (society_id, email, password_hash), fetch_one=True)
        return result['id'] if result else None
    except Exception as e:
        print(f"Error creating society admin: {e}")
        return None


def update_society(society_id, data):
    """Update society details"""
    try:
        query = """
            UPDATE societies 
            SET name = %s, email = %s, phone = %s, address = %s,
                secretary_name = %s, secretary_phone = %s
            WHERE id = %s
            RETURNING id
        """
        params = (
            data.get('name'), data.get('email'), data.get('phone'),
            data.get('address'), data.get('sec_name'), data.get('sec_phone'),
            society_id
        )
        result = db.execute_query(query, params, fetch_one=True)
        return result['id'] if result else None
    except Exception as e:
        print(f"Error updating society: {e}")
        return None


def delete_society(society_id):
    """Delete a society"""
    try:
        query = "DELETE FROM societies WHERE id = %s RETURNING id"
        result = db.execute_query(query, (society_id,), fetch_one=True)
        return result['id'] if result else None
    except Exception as e:
        print(f"Error deleting society: {e}")
        return None