from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base

class RecipeJob(Base):
    """Model for tracking async recipe generation jobs"""
    __tablename__ = "recipe_jobs"

    id = Column(String, primary_key=True)  # UUID
    # Exactly one of user_id/device_id is always set: user_id for
    # authenticated jobs, device_id for guest jobs. result_json is populated
    # only for guest jobs — authenticated jobs continue using recipe_id.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    device_id = Column(String, nullable=True, index=True)
    status = Column(String(20), nullable=False, default="pending")  # pending, processing, completed, failed
    job_type = Column(String(20), nullable=False)  # generate, modify

    # Request data
    prompt = Column(Text, nullable=False)
    preferences = Column(JSON, nullable=True)

    # For modification jobs
    original_recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=True)
    modification_prompt = Column(Text, nullable=True)

    # Results
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=True)
    result_json = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Metadata
    generation_metadata = Column(JSON, nullable=True)
    progress = Column(Integer, default=0)  # 0-100
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="recipe_jobs")
    recipe = relationship("Recipe", foreign_keys=[recipe_id])
    original_recipe = relationship("Recipe", foreign_keys=[original_recipe_id])

    def to_dict(self):
        """Convert job to dictionary for API responses"""
        return {
            "id": self.id,
            "status": self.status,
            "job_type": self.job_type,
            "prompt": self.prompt,
            "progress": self.progress,
            "recipe_id": str(self.recipe_id) if self.recipe_id else None,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "estimated_completion": self._estimate_completion()
        }
    
    def _estimate_completion(self):
        """Estimate completion time based on current progress"""
        if self.status == "completed" or self.status == "failed":
            return None
        if self.progress == 0:
            return "2-3 minutes"
        elif self.progress < 50:
            return "1-2 minutes"
        else:
            return "30-60 seconds"