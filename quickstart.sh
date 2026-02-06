#!/bin/bash

echo "🚀 Discord Role Bot - Quick Start"
echo "================================"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "📝 Creating .env from template..."
    cp .env.example .env
    echo "✅ Created .env file"
    echo ""
    echo "⚠️  Please edit .env with your actual values:"
    echo "   - DISCORD_TOKEN"
    echo "   - DISCORD_CLIENT_ID"
    echo "   - CLOUDINARY credentials"
    echo "   - SECRET_KEY (generate a random string)"
    echo ""
    echo "Then run this script again."
    exit 1
fi

echo "✅ .env file found"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
fi

echo "📦 Activating virtual environment..."
source venv/bin/activate

echo "📦 Installing dependencies..."
pip install -r requirements.txt --quiet

echo ""
echo "🗄️  Setting up database..."
python manage.py migrate

echo ""
echo "🔧 Initializing defaults..."
python manage.py init_defaults

echo ""
echo "✅ Setup complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Make sure your .env has correct Discord token and Cloudinary credentials"
echo "   2. Run: python bot/main.py (to start the bot)"
echo "   3. Run: python manage.py runserver (to start Django - in another terminal)"
echo "   4. Invite bot to your Discord server"
echo "   5. Give yourself @BotAdmin role"
echo "   6. DM bot: @BotName getaccess"
echo ""
echo "🌐 Local web admin will be at: http://localhost:8000/admin/"
echo ""
