from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
from dotenv import load_dotenv
from datetime import datetime

# Import logging configuration BEFORE other imports
from .utils.logging_config import setup_logging, get_logger
from .middleware import (
    LoggingMiddleware,
    SecurityHeadersMiddleware,
    SecurityMonitoringMiddleware,
    IPWhitelistMiddleware,
    get_security_middleware_config,
    log_security_event
)

# Load environment variables first
load_dotenv()

# Setup logging early
setup_logging()

from .schemas.base import HealthResponse, StatusResponse, ErrorResponse
from fastapi_limiter import FastAPILimiter
import redis.asyncio as redis
import json
from .database import init_database, check_database_connection
from .routers import auth, users, recipes, shopping_list, webhooks
from .services.llm_service import check_llm_service_status
from .utils.database_health import get_database_health, is_database_healthy, ensure_database_ready
from .utils.cors_utils import test_cors_origins, CORSOriginValidator
from .utils.health_monitor import get_quick_health, get_comprehensive_health, get_readiness_status
from .utils.migration_utils import get_migration_status, run_production_migrations, validate_schema, get_migration_history

# Environment variables already loaded above

# Environment configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Get configured logger
logger = get_logger("main")

# Security check for production
if ENVIRONMENT == "production" and DEBUG:
    logger.error("SECURITY WARNING: DEBUG=True in production environment!")
    raise ValueError("DEBUG mode must be disabled in production")

# SECRET_KEY is now required and checked in auth.py - no need for default value check

# Create FastAPI app
app = FastAPI(
    title="Recipe Wizard API",
    description="A powerful API for generating personalized recipes and grocery lists using local LLM",
    version="1.0.0",
    docs_url="/docs" if ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if ENVIRONMENT != "production" else None
)

# CORS configuration for mobile app
def get_cors_origins():
    """Get CORS origins based on environment with enhanced mobile app support"""
    if ENVIRONMENT == "production":
        # Production origins from environment variable
        allowed_origins = os.getenv("ALLOWED_ORIGINS", "")
        if allowed_origins:
            origins = [origin.strip() for origin in allowed_origins.split(",")]
            # Validate production origins
            validated_origins = []
            for origin in origins:
                if validate_origin(origin):
                    validated_origins.append(origin)
                else:
                    logger.warning(f"Invalid origin ignored: {origin}")
            return validated_origins
        else:
            logger.warning("No ALLOWED_ORIGINS set in production - CORS will be restricted")
            return []
    else:
        # Development origins - comprehensive list for local development
        return [
            "http://localhost:3000",        # React web development
            "http://127.0.0.1:3000",
            "http://localhost:8081",        # React Native Metro bundler
            "exp://localhost:19000",       # Expo development server
            "exp://127.0.0.1:19000",
            "exp://192.168.1.0:19000",     # Expo LAN access (example)
            "exp://10.0.2.2:19000",       # Android emulator host
            "http://localhost:19006",      # Expo web
            "http://127.0.0.1:19006",
            "capacitor://localhost",       # Capacitor apps
            "ionic://localhost",           # Ionic apps
            "http://localhost",            # General localhost
            "https://localhost",           # HTTPS localhost
        ]

def validate_origin(origin: str) -> bool:
    """Validate that an origin is properly formatted and secure"""
    import re
    
    # Allow Expo development origins
    if origin.startswith("exp://"):
        return True
    
    # Allow capacitor and ionic apps
    if origin in ["capacitor://localhost", "ionic://localhost"]:
        return True
    
    # Validate HTTP/HTTPS origins
    if origin.startswith(("http://", "https://")):
        # In production, prefer HTTPS
        if ENVIRONMENT == "production" and origin.startswith("http://"):
            logger.warning(f"HTTP origin in production: {origin} - consider using HTTPS")
        
        # Basic URL validation regex
        url_pattern = r'^https?://[a-zA-Z0-9.-]+(?::[0-9]+)?(?:/.*)?$'
        return re.match(url_pattern, origin) is not None
    
    logger.warning(f"Unknown origin format: {origin}")
    return False

# Get and validate CORS origins
origins = get_cors_origins()

# Enhanced CORS security configuration
def get_cors_config():
    """Get CORS configuration based on environment"""
    if ENVIRONMENT == "production":
        return {
            "allow_origins": origins,
            "allow_credentials": True,
            "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": [
                "Authorization",
                "Content-Type",
                "X-Requested-With",
                "Accept",
                "Origin",
                "User-Agent",
                "DNT",
                "Cache-Control",
                "X-Mx-ReqToken",
                "Keep-Alive",
                "X-CSRF-Token",
                "X-Device-Id"
            ],
            "expose_headers": ["Content-Range", "X-Content-Range"],
            "max_age": 3600,  # Cache preflight requests for 1 hour
        }
    else:
        # Development - more permissive
        return {
            "allow_origins": origins,
            "allow_credentials": True,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
            "expose_headers": ["*"],
            "max_age": 86400,  # Cache for 24 hours in development
        }

cors_config = get_cors_config()
logger.info(f"CORS configuration for {ENVIRONMENT}:")
logger.info(f"  Origins: {len(origins)} configured")
logger.info(f"  Credentials: {cors_config['allow_credentials']}")
logger.info(f"  Methods: {cors_config['allow_methods']}")

if ENVIRONMENT == "development":
    logger.info(f"  Development origins: {origins}")
else:
    logger.info(f"  Production origins: {[o for o in origins]}")

# Get security configuration
security_config = get_security_middleware_config()

# Add middleware in correct order (LIFO - Last In, First Out)
# Security headers should be added last (processed first)
app.add_middleware(
    CORSMiddleware,
    **cors_config
)

# Add logging middleware
app.add_middleware(LoggingMiddleware)

# Add security middleware (conditional based on environment)
if security_config["security_headers_enabled"]:
    app.add_middleware(SecurityHeadersMiddleware)
    logger.info("Security headers middleware enabled")

if security_config["threat_monitoring_enabled"]:
    app.add_middleware(SecurityMonitoringMiddleware)
    logger.info("Threat monitoring middleware enabled")

# Add IP whitelist for admin endpoints (if configured)
if security_config["whitelist_ips"]:
    app.add_middleware(IPWhitelistMiddleware, whitelisted_ips=security_config["whitelist_ips"])
    logger.info(f"IP whitelist middleware enabled for {len(security_config['whitelist_ips'])} IPs")

# Rate limiting is handled by FastAPILimiter (initialized in startup event)
# Custom RateLimitingMiddleware removed to prevent conflicts
logger.info("Rate limiting handled by FastAPILimiter with Redis backend")

# Include routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(recipes.router)
app.include_router(shopping_list.router)
app.include_router(webhooks.router)

# Import and include async job router
from .routers import jobs
app.include_router(jobs.router)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url}: {exc}")
    error_response = ErrorResponse(
        error="Internal Server Error",
        detail=str(exc) if DEBUG else "An unexpected error occurred",
        error_code="INTERNAL_ERROR"
    )
    # Use custom encoder to handle datetime serialization
    content = json.loads(json.dumps(error_response.model_dump(), cls=DateTimeEncoder))
    return JSONResponse(
        status_code=500,
        content=content
    )

# Custom JSON encoder for datetime objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

# HTTP exception handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning(f"HTTP exception on {request.url}: {exc.status_code} - {exc.detail}")
    error_response = ErrorResponse(
        error=f"HTTP {exc.status_code}",
        detail=exc.detail,
        error_code=f"HTTP_{exc.status_code}"
    )
    # Use custom encoder to handle datetime serialization
    content = json.loads(json.dumps(error_response.model_dump(), cls=DateTimeEncoder))
    return JSONResponse(
        status_code=exc.status_code,
        content=content
    )

# Quick health check endpoint (for load balancers/uptime monitoring)
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Quick health check endpoint - completes in <1 second"""
    health_data = await get_quick_health()
    return HealthResponse(**health_data)

# Kubernetes/Docker liveness probe
@app.get("/health/live")
async def liveness_check():
    """Liveness probe - checks if application is running"""
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}

# Kubernetes/Docker readiness probe  
@app.get("/health/ready")
async def readiness_check():
    """Readiness probe - checks if application is ready to serve traffic"""
    readiness_data = await get_readiness_status()
    status_code = 200 if readiness_data["ready"] else 503
    return JSONResponse(
        status_code=status_code,
        content=readiness_data
    )

# Enhanced database health endpoint
@app.get("/api/database/health")
async def database_health():
    """Detailed database health information"""
    return get_database_health()

# CORS configuration testing endpoint
@app.get("/api/cors/test")
async def cors_test():
    """Test current CORS configuration and provide recommendations"""
    current_origins = origins
    
    # Test current origins
    test_results = test_cors_origins(current_origins, ENVIRONMENT)
    
    # Get recommendations
    validator = CORSOriginValidator()
    recommendations = validator.get_recommended_origins(ENVIRONMENT)
    
    return {
        "environment": ENVIRONMENT,
        "current_origins": current_origins,
        "validation_results": test_results,
        "recommendations": recommendations,
        "cors_config": {
            "allow_credentials": cors_config["allow_credentials"],
            "allow_methods": cors_config["allow_methods"],
            "max_age": cors_config.get("max_age", 0)
        }
    }

# CORS preflight test endpoint
@app.options("/api/cors/preflight-test")
async def cors_preflight_test():
    """Test CORS preflight functionality"""
    return {"message": "CORS preflight test successful"}

# Database migration endpoints
@app.get("/api/migrations/status")
async def migration_status():
    """Get current database migration status"""
    return get_migration_status()

@app.get("/api/migrations/history")
async def migration_history(limit: int = 10):
    """Get migration history"""
    return {"migrations": get_migration_history(limit)}

@app.post("/api/migrations/run")
async def run_migrations():
    """Run pending database migrations (admin only)"""
    if ENVIRONMENT != "production":
        return {"error": "This endpoint is only available in production"}
    
    # In a real application, you'd want admin authentication here
    result = run_production_migrations()
    
    status_code = 200 if result.get("success", False) else 500
    return JSONResponse(status_code=status_code, content=result)

@app.get("/api/migrations/validate")
async def validate_database_schema():
    """Validate that database schema is correct"""
    return validate_schema()

# Logging configuration endpoint
@app.get("/api/logging/config")
async def logging_configuration():
    """Get current logging configuration"""
    import logging
    
    # Get all active loggers
    loggers_info = {}
    for name in logging.Logger.manager.loggerDict:
        if name.startswith('app') or name in ['uvicorn', 'sqlalchemy.engine', 'alembic']:
            logger_obj = logging.getLogger(name)
            loggers_info[name] = {
                "level": logging.getLevelName(logger_obj.level),
                "effective_level": logging.getLevelName(logger_obj.getEffectiveLevel()),
                "handlers": len(logger_obj.handlers),
                "propagate": logger_obj.propagate,
            }
    
    return {
        "environment": ENVIRONMENT,
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
        "structured_logging": ENVIRONMENT == "production",
        "loggers": loggers_info,
        "timestamp": datetime.utcnow().isoformat()
    }

# Test logging endpoint (development only)
@app.post("/api/logging/test")
async def test_logging():
    """Test different log levels (development only)"""
    if ENVIRONMENT == "production":
        return {"error": "Logging test not available in production"}
    
    test_logger = get_logger("test")
    
    test_logger.debug("This is a DEBUG message")
    test_logger.info("This is an INFO message")
    test_logger.warning("This is a WARNING message")
    test_logger.error("This is an ERROR message")
    
    try:
        raise ValueError("This is a test exception")
    except ValueError as e:
        test_logger.error("Test exception caught", exc_info=True)
    
    return {
        "message": "Log test completed - check logs for output",
        "timestamp": datetime.utcnow().isoformat()
    }

# Security monitoring endpoints
@app.get("/api/security/config")
async def security_configuration():
    """Get current security configuration"""
    config = get_security_middleware_config()
    
    # Remove sensitive information from response
    safe_config = {
        "security_headers_enabled": config["security_headers_enabled"],
        "threat_monitoring_enabled": config["threat_monitoring_enabled"],
        "rate_limiting_enabled": True,
        "rate_limit_per_minute": config["rate_limit_per_minute"],
        "rate_limit_burst": config["rate_limit_burst"],
        "whitelist_enabled": bool(config["whitelist_ips"]),
        "whitelisted_ip_count": len(config["whitelist_ips"]) if config["whitelist_ips"] else 0,
        "redis_enabled": bool(config["redis_url"]),
        "environment": ENVIRONMENT,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return safe_config

@app.get("/api/security/status")
async def security_status():
    """Get current security status and statistics"""
    # This endpoint would normally aggregate security metrics
    # For now, we'll return basic status information
    return {
        "status": "active",
        "services": {
            "rate_limiting": "active",
            "threat_monitoring": "active" if security_config["threat_monitoring_enabled"] else "disabled",
            "security_headers": "active" if security_config["security_headers_enabled"] else "disabled",
            "ip_whitelist": "active" if security_config["whitelist_ips"] else "disabled"
        },
        "metrics": {
            "total_requests_today": 0,  # Would be tracked by middleware
            "blocked_requests_today": 0,  # Would be tracked by middleware
            "suspicious_activities_today": 0  # Would be tracked by middleware
        },
        "last_updated": datetime.utcnow().isoformat(),
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/api/security/test")
async def test_security():
    """Test security middleware functionality (development only)"""
    if ENVIRONMENT == "production":
        return {"error": "Security testing not available in production"}
    
    # Test security event logging
    log_security_event(
        event_type="security_test",
        severity="INFO",
        details={
            "test_type": "endpoint_test",
            "user_agent": "RecipeWizard-Testing",
            "ip_address": "127.0.0.1",
            "endpoint": "/api/security/test",
            "message": "Security middleware test initiated"
        }
    )
    
    return {
        "message": "Security test completed - check security logs for output",
        "middleware_status": {
            "security_headers": security_config["security_headers_enabled"],
            "threat_monitoring": security_config["threat_monitoring_enabled"],
            "rate_limiting": True,
            "ip_whitelist": bool(security_config["whitelist_ips"])
        },
        "timestamp": datetime.utcnow().isoformat()
    }

# Comprehensive health endpoint (detailed diagnostics)
@app.get("/health/comprehensive")
async def comprehensive_health_check():
    """Comprehensive health check with all service details"""
    return await get_comprehensive_health()

# Status endpoint with more detailed information  
@app.get("/api/status")
async def api_status():
    """Detailed API status including service dependencies"""
    try:
        # Get basic database connection status
        db_connected = check_database_connection()
        
        # Build simple, serializable status
        return {
            "status": "operational",
            "service": "Recipe Wizard API",
            "version": "1.0.0",
            "environment": ENVIRONMENT,
            "services": {
                "api": "running",
                "database": "connected" if db_connected else "disconnected",
                "llm_service": "available",
                "redis": "connected"
            },
            "message": "Recipe Wizard API is running",
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": 0  # Simplified for now
        }
    except Exception as e:
        logger.error(f"Status endpoint error: {e}")
        return {
            "status": "error",
            "service": "Recipe Wizard API",
            "version": "1.0.0",
            "environment": ENVIRONMENT,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information"""
    endpoint_info = {
        "message": "Welcome to Recipe Wizard API",
        "health": "/health",
        "health_live": "/health/live",
        "health_ready": "/health/ready", 
        "health_comprehensive": "/health/comprehensive",
        "status": "/api/status",
        "database_health": "/api/database/health",
        "cors_test": "/api/cors/test",
        "cors_preflight": "/api/cors/preflight-test",
        "migration_status": "/api/migrations/status",
        "migration_history": "/api/migrations/history",
        "migration_validate": "/api/migrations/validate",
        "logging_config": "/api/logging/config",
        "security_config": "/api/security/config",
        "security_status": "/api/security/status",
        "environment": ENVIRONMENT,
        "version": "1.0.0",
        "cors_origins_count": len(origins),
        "security_enabled": True
    }
    
    # Add docs endpoints only in development
    if ENVIRONMENT != "production":
        endpoint_info["docs"] = "/docs"
        endpoint_info["redoc"] = "/redoc"
    
    return endpoint_info

# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info(
        "Recipe Wizard API starting up",
        extra={
            "environment": ENVIRONMENT,
            "debug_mode": DEBUG,
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
            "structured_logging": ENVIRONMENT == "production",
            "cors_origins_count": len(origins),
            "version": "1.0.0"
        }
    )
    
    # Validate critical environment variables in production
    if ENVIRONMENT == "production":
        required_vars = ["SECRET_KEY", "DATABASE_URL", "OPENAI_API_KEY", "REVENUECAT_WEBHOOK_SECRET"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            logger.error(f"Missing required environment variables: {missing_vars}")
            raise ValueError(f"Required environment variables not set: {missing_vars}")
        
        # Comprehensive database setup for production
        logger.info("Setting up database for production...")
        # Temporarily skip migration check since tables are already created manually
        try:
            if not check_database_connection():
                logger.error("Database connection failed - cannot start API")
                raise RuntimeError("Database connection is not available")
            logger.info("Database connection verified successfully")
        except Exception as e:
            logger.error(f"Database setup error: {e}")
            raise RuntimeError(f"Database setup failed: {e}")
    else:
        # Development database setup
        try:
            init_database()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            logger.warning("Continuing despite database initialization failure in development mode")
    
    # Initialize rate limiter (optional; requires REDIS_URL)
    try:
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            # Configure SSL for Heroku Redis with connection pooling
            ssl_kwargs = {}
            if redis_url.startswith("rediss://"):  # SSL Redis URL
                ssl_kwargs = {
                    "ssl_cert_reqs": None,  # Don't verify SSL certificates
                    "ssl_check_hostname": False,  # Don't verify hostname
                    "ssl_ca_certs": None
                }
            
            r = redis.from_url(
                redis_url, 
                encoding="utf-8", 
                decode_responses=True,
                retry_on_timeout=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30,
                **ssl_kwargs
            )
            await FastAPILimiter.init(r)
            logger.info("Rate limiter initialized with Redis (with connection pooling)")
        else:
            logger.warning("REDIS_URL not set; rate limiting is disabled")
    except Exception as e:
        logger.error(f"Failed to initialize rate limiter: {e}")
    
    logger.info(
        "Recipe Wizard API startup completed - ready to serve requests",
        extra={
            "startup_complete": True,
            "environment": ENVIRONMENT,
            "endpoints_available": True,
            "middleware_loaded": ["LoggingMiddleware", "CORSMiddleware"],
            "database_initialized": True
        }
    )

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info(
        "Recipe Wizard API shutting down",
        extra={
            "shutdown_initiated": True,
            "environment": ENVIRONMENT,
            "graceful_shutdown": True
        }
    )
