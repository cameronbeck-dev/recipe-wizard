# Recipe Wizard API - Heroku Deployment Guide

## Pre-Deployment Security Checklist ✅

### Environment Variables to Set in Heroku

```bash
# Required Production Environment Variables
heroku config:set SECRET_KEY=770da34509d73bce13ce6903c671ee0368cc6471b9471b8b533563e6b3b88771
heroku config:set ENVIRONMENT=production
heroku config:set DEBUG=False
heroku config:set OPENAI_API_KEY=your-openai-key-here

# Database (auto-configured by Heroku Postgres add-on)
heroku config:set DATABASE_URL=postgresql://...

# CORS Configuration - CRITICAL for mobile app access
heroku config:set ALLOWED_ORIGINS="https://your-app.herokuapp.com,exp://your-expo-app,https://your-custom-domain.com"

# Example for Recipe Wizard:
# heroku config:set ALLOWED_ORIGINS="https://recipewizard.herokuapp.com,exp://recipewizard,https://app.recipewizard.com"

# Optional: Redis for rate limiting
heroku config:set REDIS_URL=redis://...

# API Configuration
heroku config:set API_HOST=0.0.0.0
heroku config:set API_PORT=8000
heroku config:set DEFAULT_MODEL_FREE=gpt-5.6-luna
heroku config:set DEFAULT_MODEL_PAID=gpt-5.6-terra
```

### Security Features Implemented ✅

1. **Strong Secret Key Generation**: 256-bit cryptographically secure key
2. **Environment-Based Configuration**: Separate dev/prod settings
3. **Production Security Validation**: Prevents weak keys in production
4. **Debug Mode Protection**: Automatically disabled in production
5. **Secure Error Handling**: Sensitive details hidden in production
6. **CORS Security**: Environment-specific origin configuration
7. **Required Variables Validation**: Startup fails if critical vars missing

### Files Secured ✅

- `.env` files added to `.gitignore`
- Production configuration template created
- Secret key generation script provided
- Development vs production separation implemented

## Next Steps

1. Set up production database configuration
2. Configure CORS for mobile app domain
3. Add comprehensive health checks
4. Set up database migrations
5. Configure production logging
6. Add rate limiting and security middleware

## Critical Security Notes ⚠️

- **NEVER** commit `.env` files to git
- **ALWAYS** use strong, unique secret keys in production
- **VERIFY** CORS origins match your actual domains
- **MONITOR** API usage and costs
- **ROTATE** secret keys periodically

## Emergency Procedures

### If Secret Key is Compromised
```bash
# Generate new key
python scripts/generate_secret.py

# Update in Heroku
heroku config:set SECRET_KEY=new-secure-key-here

# Restart app
heroku restart
```

### If Database Issues Occur
```bash
# Check database status
heroku pg:info

# Check logs
heroku logs --tail

# Run migrations
heroku run alembic upgrade head
```
