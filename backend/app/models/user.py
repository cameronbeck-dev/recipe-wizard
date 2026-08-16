from sqlalchemy import Column, String, Boolean, Integer, BigInteger, JSON, Text, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from datetime import datetime, timezone
from .base import BaseModel

class User(BaseModel):
    """User model for authentication and profile management"""
    
    __tablename__ = "users"
    
    # Authentication fields
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    
    # Profile fields
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    
    # User preferences for recipe generation (stored as JSON)
    units = Column(String(20), default='metric', nullable=False)  # 'metric' or 'imperial'
    grocery_categories = Column(JSON, nullable=True)  # List of custom grocery categories
    default_servings = Column(Integer, default=4, nullable=False)
    preferred_difficulty = Column(String(20), nullable=True)  # 'easy', 'medium', 'hard'
    max_cook_time = Column(Integer, nullable=True)  # in minutes
    max_prep_time = Column(Integer, nullable=True)  # in minutes
    
    # Dietary preferences (stored as JSON arrays)
    dietary_restrictions = Column(JSON, nullable=True)  # ['vegetarian', 'gluten-free', etc.]
    allergens = Column(JSON, nullable=True)  # ['nuts', 'shellfish', etc.]
    dislikes = Column(JSON, nullable=True)  # ingredients user doesn't like
    
    # Free-text preferences
    additional_preferences = Column(Text, nullable=True)
    
    # UI preferences
    theme_preference = Column(String(20), default='system', nullable=False)  # 'light', 'dark', 'system'

    # Premium/subscription tracking (source of truth for RevenueCat entitlement state)
    premium_expires_at = Column(DateTime(timezone=True), nullable=True)
    revenuecat_customer_id = Column(String(255), nullable=True, index=True)
    premium_product_id = Column(String(255), nullable=True)  # diagnostics only
    premium_event_at_ms = Column(BigInteger, nullable=True)  # last-applied RevenueCat event timestamp

    # Relationships
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    saved_recipes = relationship("SavedRecipe", back_populates="user", cascade="all, delete-orphan")
    created_recipes = relationship("Recipe", back_populates="created_by", cascade="all, delete-orphan")
    recipe_jobs = relationship("RecipeJob", back_populates="user", cascade="all, delete-orphan")
    shopping_lists = relationship("ShoppingList", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', username='{self.username}')>"

    @hybrid_property
    def is_premium(self) -> bool:
        if self.premium_expires_at is None:
            return False
        expires_at = self.premium_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at > datetime.now(timezone.utc)

    @property
    def full_name(self):
        """Return full name or username as fallback"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.username:
            return self.username
        else:
            return self.email.split('@')[0]
    
    def get_preference_context(self) -> str:
        """Generate LLM prompt context from user preferences"""
        context = []
        
        # Units
        unit_desc = 'kg, g, ml, l, °C' if self.units == 'metric' else 'lbs, oz, cups, tablespoons, °F'
        context.append(f"Use {self.units} measurements ({unit_desc})")
        
        # Servings
        context.append(f"Recipe should serve {self.default_servings} people")
        
        # Difficulty
        if self.preferred_difficulty:
            context.append(f"Prefer {self.preferred_difficulty} difficulty level recipes")
        
        # Time constraints
        if self.max_cook_time:
            context.append(f"Maximum cooking time: {self.max_cook_time} minutes")
        if self.max_prep_time:
            context.append(f"Maximum prep time: {self.max_prep_time} minutes")
        
        # Dietary restrictions
        if self.dietary_restrictions:
            context.append(f"Dietary requirements: {', '.join(self.dietary_restrictions)}")
        
        # Allergens
        if self.allergens:
            context.append(f"MUST AVOID these allergens: {', '.join(self.allergens)}")
        
        # Dislikes
        if self.dislikes:
            context.append(f"Avoid these ingredients: {', '.join(self.dislikes)}")
        
        # Grocery categories
        if self.grocery_categories:
            context.append(f"Organize grocery list by these categories: {', '.join(self.grocery_categories)}")
        
        # Additional preferences
        if self.additional_preferences and self.additional_preferences.strip():
            context.append(f"Additional preferences: {self.additional_preferences.strip()}")
        
        return f"\n\nUser Preferences:\n" + "\n".join(f"• {item}" for item in context) if context else ""