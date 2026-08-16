from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import os
import uuid
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import TokenData
from ..constants import DEFAULT_GROCERY_CATEGORIES

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is required but not set")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))  # 7 days

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Token bearer
security = HTTPBearer()

# Authentication utilities
class AuthUtils:
    """Utility class for authentication operations"""
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a plain password against its hash"""
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """Hash a password using bcrypt"""
        return pwd_context.hash(password)
    
    @staticmethod
    def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def verify_token(token: str) -> TokenData:
        """Verify and decode JWT token"""
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id: Optional[int] = payload.get("user_id")
            email: Optional[str] = payload.get("sub")  # Subject
            
            if email is None or user_id is None:
                raise credentials_exception
                
            token_data = TokenData(user_id=user_id, email=email)
            return token_data
            
        except JWTError:
            raise credentials_exception
    
    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
        """Authenticate user with email and password"""
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            return None
            
        if not AuthUtils.verify_password(password, user.hashed_password):
            return None
            
        return user
    
    @staticmethod
    def get_user_by_email(db: Session, email: str) -> Optional[User]:
        """Get user by email address"""
        return db.query(User).filter(User.email == email).first()
    
    @staticmethod
    def get_user_by_username(db: Session, username: str) -> Optional[User]:
        """Get user by username"""
        return db.query(User).filter(User.username == username).first()
    
    @staticmethod
    def create_user(
        db: Session, 
        email: str, 
        password: str, 
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        **kwargs
    ) -> User:
        """Create a new user with default preferences"""
        # Hash the password
        hashed_password = AuthUtils.get_password_hash(password)
        
        # Create user with defaults
        user_data = {
            'email': email,
            'hashed_password': hashed_password,
            'username': username,
            'first_name': first_name,
            'last_name': last_name,
            'is_active': True,
            'is_verified': False,  # Could implement email verification later
            'units': 'metric',
            'grocery_categories': DEFAULT_GROCERY_CATEGORIES,
            'default_servings': 4,
            'dietary_restrictions': [],
            'allergens': [],
            'dislikes': [],
            'additional_preferences': '',
            'theme_preference': 'system',
            **kwargs
        }
        
        user = User(**user_data)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

# FastAPI Dependencies for authentication
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    FastAPI dependency to get current authenticated user.
    Validates JWT token and returns the user object.
    """
    # Extract token from credentials
    token = credentials.credentials
    
    # Verify token and get user data
    token_data = AuthUtils.verify_token(token)
    
    # Get user from database
    user = db.query(User).filter(User.id == token_data.user_id).first()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    return user

async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    FastAPI dependency to get current active user.
    Adds an additional check for active status.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Inactive user"
        )
    return current_user

# Optional authentication (for endpoints that work with or without auth)
async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Optional authentication dependency.
    Returns user if authenticated, None if not.
    """
    if not credentials:
        return None
    
    try:
        token_data = AuthUtils.verify_token(credentials.credentials)
        user = db.query(User).filter(User.id == token_data.user_id).first()
        
        if user and user.is_active:
            return user
        return None
        
    except HTTPException:
        return None

# Guest identity (for unauthenticated recipe generation)
async def get_device_id(
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id")
) -> Optional[str]:
    """
    Optional guest-device identity dependency.

    Returns None if the header is absent. Raises 400 if present but not a
    valid UUID — strict validation bounds guest_usage row cardinality and
    Redis key cardinality against a trivially-scripted flood.
    """
    if not x_device_id:
        return None

    try:
        uuid.UUID(x_device_id)
    except ValueError:
        # detail is a plain string, not a dict — the app's global
        # HTTPException handler builds an ErrorResponse whose `detail`
        # field is typed `str`; a dict there breaks the handler.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="INVALID_DEVICE_ID: X-Device-Id must be a valid UUID"
        )

    return x_device_id

# Utility functions for token creation
def create_access_token_for_user(user: User) -> Dict[str, Any]:
    """Create access token for a user with proper payload"""
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Create token payload
    token_payload = {
        "sub": user.email,  # Subject (standard JWT claim)
        "user_id": user.id,
        "username": user.username,
        "is_active": user.is_active,
    }
    
    access_token = AuthUtils.create_access_token(
        data=token_payload, 
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # seconds
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "firstName": user.first_name,
            "lastName": user.last_name,
            "isActive": user.is_active,
        }
    }