# Recipe Wizard 🪄

> **Create amazing recipes with just a few words**

Recipe Wizard is a cross-platform mobile application that generates personalized recipes and grocery lists from simple user prompts using OpenAI via a FastAPI backend. Transform casual requests like "creamy chicken pasta with sundried tomatoes" into structured grocery lists and detailed recipes.

## ✨ Features

### Core Features ✅ **IMPLEMENTED**
- **Natural Language Input**: Describe your recipe idea in plain English
- **Smart Grocery Lists**: Organized by category with checkable items
- **Detailed Instructions**: Step-by-step cooking guidance with timing
- **Recipe History**: Complete conversation history and saved favorites
- **Cross-Platform**: Works on iOS, Android, and Web
- **User Preferences**: Comprehensive dietary restrictions and cooking preferences
- **Authentication**: Full user registration and login system

### Advanced Features ✅ **IMPLEMENTED**
- **Tab Navigation**: Intuitive bottom tab bar with four core sections
- **Shopping List Management**: Dedicated tab with drag-to-reorder and smart categorization
- **Profile Management**: Complete user settings and preferences
- **Measurement Units**: Metric/Imperial conversion support
- **Dietary Restrictions**: Vegetarian, vegan, gluten-free, allergen management
- **Recipe Customization**: Default servings, difficulty preferences
- **Grocery Categories**: Customizable ingredient organization with drag-and-drop
- **Dark/Light Theme**: System-aware theme with manual toggle
- **Offline Support**: Local storage for preferences and saved recipes
- **Real-time Sync**: Authentication context with persistent login state

## 🛠 Tech Stack

### Frontend (Mobile App) ✅ **COMPLETED**
- **React Native** with **Expo 53** - Cross-platform mobile development
- **TypeScript** - Type-safe development with comprehensive API types
- **Expo Router 5** - File-based navigation with complete user flow
- **Custom Theme System** - Light/dark mode with AsyncStorage persistence
- **Material Community Icons** - Consistent iconography
- **Performance Optimized** - Memoization and proper lifecycle management
- **React Native Paper** - Material Design component library
- **Keyboard Aware ScrollView** - Enhanced keyboard handling

### Backend (API Server) ✅ **OPERATIONAL**
- **FastAPI** - Modern Python web framework with complete API structure
- **PostgreSQL** - Robust relational database with migrations
- **SQLAlchemy** - Python SQL toolkit and ORM
- **Alembic** - Database migration tool (migrations implemented)
- **OpenAI API** - AI recipe generation via two-tier configurable models (`DEFAULT_MODEL_FREE` / `DEFAULT_MODEL_PAID`), selected per-request by subscription status
- **JWT** - Secure authentication system with token refresh
- **Pydantic** - Data validation and serialization
- **Rate Limiting** - Redis-based request throttling
- **CORS** - Configured for mobile app integration
- **Health Monitoring** - Comprehensive health check endpoints

## 🚀 Quick Start

### Prerequisites

- **Node.js** (v18 or higher)
- **Python** (v3.8 or higher)
- **Expo CLI** (`npm install -g @expo/cli`)
- **PostgreSQL** (for backend database)
- **Redis** (for rate limiting - optional for development)
- **OpenAI API Key** (for OpenAI recipe generation)

### Setup Instructions

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd RecipeWizard
   ```

2. **Setup Mobile App**
   ```bash
   cd mobile
   npm install
   npm start
   ```

3. **Setup Backend** (Required for full functionality)
   ```bash
   cd backend

   # Create virtual environment
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # venv\Scripts\activate   # Windows

   # Install dependencies
   pip install -r requirements.txt

   # Setup environment variables
   cp .env.example .env
   # Edit .env with your configuration (see below)

   # Setup database (PostgreSQL must be running)
   # Create database: createdb recipewizard

   # Run database migrations
   alembic upgrade head

   # Start the development server
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

4. **Configure Environment Variables** (Required)

   **Backend (.env file):**
   ```env
   # Database Configuration
   DATABASE_URL=postgresql://user:password@localhost:5432/recipewizard

   # Security
   SECRET_KEY=your-secret-key-here
   ACCESS_TOKEN_EXPIRE_MINUTES=30

   # OpenAI Integration (REQUIRED)
   OPENAI_API_KEY=your-openai-api-key-here
   DEFAULT_MODEL_FREE=gpt-5.6-luna
DEFAULT_MODEL_PAID=gpt-5.6-terra

   # Optional: Rate Limiting
   REDIS_URL=redis://localhost:6379

   # Development
   DEBUG=True
   API_HOST=0.0.0.0
   API_PORT=8000
   ```

   **Mobile App Environment:**
   ```bash
   # Set in your shell or .bashrc/.zshrc
   export EXPO_PUBLIC_API_BASE_URL="http://localhost:8000"

   # For physical device testing, use your computer's IP:
   # export EXPO_PUBLIC_API_BASE_URL="http://192.168.1.xxx:8000"
   ```

## 📱 Development

### Mobile App Development

```bash
cd mobile

# Start Expo development server
npm start

# Run on specific platforms
npm run android    # Android emulator/device
npm run ios        # iOS simulator/device
npm run web        # Web browser

# Development tools
npx expo start --clear-cache  # Clear cache
npx tsc --noEmit              # Type checking
```

### Backend Development

```bash
cd backend

# Activate virtual environment
source venv/bin/activate

# Start development server with hot reload
uvicorn app.main:app --reload --port 8000

# Database operations
alembic upgrade head                           # Apply migrations
alembic revision --autogenerate -m "message"  # Create migration
```

## 🏗 Project Structure

```
RecipeWizard/
├── mobile/                    # React Native Expo app ✅ COMPLETED
│   ├── app/                  # Expo Router pages (complete user flow)
│   │   ├── index.tsx         # Welcome screen
│   │   ├── recipe-result.tsx # Recipe display screen
│   │   ├── _layout.tsx       # Root navigation layout
│   │   ├── (tabs)/           # Tab navigation structure ✅ NEW
│   │   │   ├── _layout.tsx   # Tab bar configuration
│   │   │   ├── prompt.tsx    # Recipe input screen (tab)
│   │   │   ├── history.tsx   # Recipe history with saved favorites
│   │   │   ├── shopping-list.tsx # Dedicated shopping list management ✅ NEW
│   │   │   └── profile.tsx   # User settings & preferences
│   │   └── auth/             # Authentication screens
│   │       ├── signin.tsx    # User sign-in
│   │       └── signup.tsx    # User registration
│   ├── components/           # Complete UI component library (12+ components)
│   │   ├── Button.tsx        # Multi-variant button
│   │   ├── TextInput.tsx     # Performance-optimized input
│   │   ├── ExpandableCard.tsx# Collapsible sections
│   │   ├── SavedRecipesSection.tsx ✅ NEW
│   │   ├── AllHistorySection.tsx   ✅ NEW
│   │   ├── CheckboxItem.tsx  # Interactive grocery list items
│   │   └── ...               # Additional specialized components
│   ├── contexts/             # React context providers ✅ NEW
│   │   └── AuthContext.tsx   # Authentication state management
│   ├── constants/            # Theme system and configuration
│   ├── services/             # Complete API client services
│   │   ├── api.ts           # Main API service
│   │   ├── auth.ts          # Authentication services
│   │   ├── preferences.ts   # User preferences management ✅ NEW
│   │   └── savedRecipes.ts  # Recipe saving functionality ✅ NEW
│   ├── types/                # Complete TypeScript definitions
│   │   ├── api.ts           # API types
│   │   └── recipe.ts        # Recipe-specific types
│   └── assets/               # Icons and resources
├── backend/                   # Python FastAPI server ✅ OPERATIONAL
│   ├── app/
│   │   ├── models/           # SQLAlchemy database models
│   │   │   └── base.py      # Base model definitions
│   │   ├── schemas/          # Pydantic API schemas
│   │   │   ├── user.py      # User data validation
│   │   │   ├── conversation.py # Recipe conversation schemas
│   │   │   └── base.py      # Base schema definitions
│   │   ├── routers/          # API endpoint definitions
│   │   │   ├── auth.py      # Authentication endpoints
│   │   │   ├── users.py     # User management
│   │   │   └── recipes.py   # Recipe generation endpoints ✅ NEW
│   │   ├── services/         # Business logic layer
│   │   │   └── llm_service.py # LLM integration service ✅ NEW
│   │   ├── utils/            # Utility functions
│   │   │   └── auth.py      # JWT authentication utilities
│   │   ├── database.py       # Database configuration
│   │   └── main.py           # FastAPI application (comprehensive)
│   ├── alembic/              # Database migrations (implemented)
│   │   └── versions/         # Migration files
│   └── requirements.txt      # Python dependencies (complete)
├── shared/                    # Shared TypeScript types
├── design/                    # UI mockups and design assets
└── docs/                      # Project documentation
```

## 🎨 Design System

The app features a modern dark UI with a subtle magical aesthetic:

- **Colors**: Dark backgrounds with blue accent colors
- **Typography**: Mix of modern sans-serif and elegant serif fonts
- **Icons**: Material Design icons with magical touches
- **Layout**: Clean, spacious design optimized for mobile

Design mockups are available in the `design/examples/` folder.

## 🔮 Core User Experience

1. **Welcome Screen**: Elegant introduction with magical visual elements
2. **Authentication**: Seamless sign-up/sign-in with user account creation
3. **Tab Navigation**: Four main tabs for core functionality:
   - **Prompt**: Natural language recipe input with AI-powered suggestions
   - **History**: Complete recipe history with saved favorites management
   - **Shopping List**: Dedicated shopping list with drag-to-reorder and categories
   - **Profile**: Comprehensive settings for dietary preferences and customization
4. **Recipe Generation**: Real-time recipe and grocery list creation via OpenAI
5. **Results**: Organized grocery list with checkboxes + detailed cooking instructions
6. **Saving**: One-tap saving to personal recipe collection with instant sync

## 🚧 Development Status

**✅ Mobile App - FULLY COMPLETED:**
- [x] Complete theme system with light/dark mode and system detection
- [x] Comprehensive component library (15+ reusable components)
- [x] Modern tab navigation with 4 core sections (Prompt, History, Shopping List, Profile)
- [x] Recipe result screen with expandable grocery lists & instructions
- [x] Recipe history screen with saved favorites management
- [x] Dedicated shopping list tab with drag-to-reorder functionality
- [x] Comprehensive profile/settings screen with user preferences
- [x] Authentication system with persistent context management
- [x] Performance optimization and comprehensive error handling
- [x] Complete API service layer with all endpoints
- [x] Full TypeScript type system for all data structures
- [x] Local storage integration for preferences and offline support
- [x] Advanced ingredient categorization and organization
- [x] Real-time shopping list state management

**✅ Backend - FULLY OPERATIONAL:**
- [x] Complete FastAPI project structure with comprehensive error handling
- [x] OpenAI OpenAI integration for intelligent recipe generation
- [x] Full database schema and models with Alembic migrations
- [x] Authentication endpoints with JWT token management and refresh
- [x] Recipe generation API endpoints with structured JSON responses
- [x] User management and preferences endpoints
- [x] Shopping list API endpoints with category management
- [x] Rate limiting with Redis and CORS configuration
- [x] Health check and status monitoring endpoints
- [x] Comprehensive error handling, logging, and security measures
- [x] Production-ready deployment configuration for Heroku

**✅ Recently Completed Features:**
- [x] Modern tab navigation architecture replacing stack navigation
- [x] Dedicated shopping list tab with advanced management features
- [x] Drag-and-drop ingredient reordering with smooth animations
- [x] Enhanced recipe history with improved saved favorites section
- [x] Comprehensive user profile and preferences management
- [x] Advanced dietary restrictions and allergen management
- [x] Measurement unit preferences (metric/imperial) with real-time conversion
- [x] Customizable grocery categories with drag-to-reorder
- [x] AI personalization with additional preferences text input
- [x] Recipe saving and unsaving with instant visual feedback
- [x] Authentication context with persistent login state and auto-refresh
- [x] OpenAI OpenAI integration replacing local LLM setup

**🔄 Optional Future Enhancements:**
- [ ] Push notifications for meal planning and reminders
- [ ] Recipe sharing and social features with friends
- [ ] Advanced meal planning calendar with weekly/monthly views
- [ ] Nutrition information integration with calorie tracking
- [ ] Smart recipe scaling and ingredient substitution suggestions
- [ ] Integration with grocery delivery services (Instacart, etc.)
- [ ] Voice input for hands-free recipe prompts
- [ ] Recipe photo capture and AI-powered analysis
- [ ] Barcode scanning for pantry inventory management
- [ ] Smart shopping list optimization by store layout
- [ ] Recipe recommendations based on available ingredients
- [ ] Export recipes to popular cooking apps and platforms

## 🧪 API Endpoints ✅ **IMPLEMENTED IN SERVICE LAYER**

```typescript
// Authentication
POST /api/auth/register
POST /api/auth/login
POST /api/auth/refresh

// Recipe Generation  
POST /api/recipes/generate
GET  /api/recipes/history
POST /api/recipes/save
DELETE /api/recipes/{id}

// User Management
GET  /api/users/profile
PUT  /api/users/settings
```

## 🔧 Environment Variables

### Backend (.env)
```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/recipewizard

# Authentication
SECRET_KEY=your-secret-key-here
ACCESS_TOKEN_EXPIRE_MINUTES=30

# OpenAI Integration
OPENAI_API_KEY=your-openai-api-key-here
DEFAULT_MODEL_FREE=gpt-5.6-luna
DEFAULT_MODEL_PAID=gpt-5.6-terra

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=True
```

### Mobile (Environment Variables)
```bash
# Set in your development environment
export EXPO_PUBLIC_API_BASE_URL="http://localhost:8000"

# Or in app.json
{
  "expo": {
    "extra": {
      "apiBaseUrl": "http://localhost:8000"
    }
  }
}
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Expo** for the excellent React Native development platform
- **FastAPI** for the modern Python web framework
- **OpenAI** for AI recipe generation
- **RevenueCat** for subscription management
- **Material Design** for the component system

---

**Built with ❤️ for home cooks everywhere**