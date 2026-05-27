from sqlalchemy import text
from app.models.base import db

class ApartmentLoader:
    @staticmethod
    def get_list(society_id=None, search=None):
        query = text("SELECT * FROM fn_apartments_list(:society_id, :search)")
        result = db.session.execute(query, {"society_id": society_id, "search": search})
        return [dict(row) for row in result.mappings()]
