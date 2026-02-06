@echo off
echo 🚀 Discord Role Bot - Quick Start
echo ================================
echo.

REM Check if .env exists
if not exist .env (
    echo ❌ .env file not found!
    echo 📝 Creating .env from template...
    copy .env.example .env
    echo ✅ Created .env file
    echo.
    echo ⚠️  Please edit .env with your actual values:
    echo    - DISCORD_TOKEN
    echo    - DISCORD_CLIENT_ID
    echo    - CLOUDINARY credentials
    echo    - SECRET_KEY (generate a random string^)
    echo.
    echo Then run this script again.
    pause
    exit /b 1
)

echo ✅ .env file found
echo.

REM Check if virtual environment exists
if not exist venv (
    echo 📦 Creating virtual environment...
    python -m venv venv
    echo ✅ Virtual environment created
)

echo 📦 Activating virtual environment...
call venv\Scripts\activate.bat

echo 📦 Installing dependencies...
pip install -r requirements.txt --quiet

echo.
echo 🗄️  Setting up database...
python manage.py migrate

echo.
echo 🔧 Initializing defaults...
python manage.py init_defaults

echo.
echo ✅ Setup complete!
echo.
echo 📋 Next steps:
echo    1. Make sure your .env has correct Discord token and Cloudinary credentials
echo    2. Run: python bot/main.py (to start the bot^)
echo    3. Run: python manage.py runserver (to start Django - in another terminal^)
echo    4. Invite bot to your Discord server
echo    5. Give yourself @BotAdmin role
echo    6. DM bot: @BotName getaccess
echo.
echo 🌐 Local web admin will be at: http://localhost:8000/admin/
echo.
pause
