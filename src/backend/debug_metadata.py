from app.db.base import Base
import app.modules.pricing.models
print("Tables:", Base.metadata.tables.keys())
