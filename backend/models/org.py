"""HOLO-RTLS — Business org config: personnel positions and site sections."""
from datetime import datetime, timezone
from backend.extensions import db


class PersonnelPosition(db.Model):
    """Configurable job titles / roles (Manager, Operator, etc.)."""
    __tablename__ = "personnel_positions"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(120), nullable=False, unique=True)
    sort_order = db.Column(db.Integer, default=0)
    is_active  = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "sort_order": self.sort_order,
            "is_active": self.is_active,
        }


class OrgSection(db.Model):
    """Business site areas (Underground, Surface, Workshop, etc.) — not map polygons."""
    __tablename__ = "org_sections"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(120), nullable=False, unique=True)
    sort_order = db.Column(db.Integer, default=0)
    is_active  = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "sort_order": self.sort_order,
            "is_active": self.is_active,
        }
