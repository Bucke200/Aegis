#!/usr/bin/env python3
"""
Quick start script for Aegis VIP Threat Monitoring Platform
"""
import os
import sys
import subprocess
import time
from pathlib import Path


def print_banner():
    """Print Aegis banner"""
    banner = """
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║     █████╗ ███████╗ ██████╗ ██╗███████╗                      ║
    ║    ██╔══██╗██╔════╝██╔════╝ ██║██╔════╝                      ║
    ║    ███████║█████╗  ██║  ███╗██║███████╗                      ║
    ║    ██╔══██║██╔══╝  ██║   ██║██║╚════██║                      ║
    ║    ██║  ██║███████╗╚██████╔╝██║███████║                      ║
    ║    ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝╚══════╝                      ║
    ║                                                               ║
    ║           VIP Threat Monitoring Platform                      ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def check_requirements():
    """Check if requirements are met"""
    print("🔍 Checking requirements...")
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ is required")
        return False
    
    print(f"✅ Python {sys.version.split()[0]}")
    
    # Check Docker
    try:
        result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ {result.stdout.strip()}")
        else:
            print("❌ Docker not found")
            return False
    except FileNotFoundError:
        print("❌ Docker not found")
        return False
    
    # Check Docker Compose
    try:
        result = subprocess.run(['docker-compose', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ {result.stdout.strip()}")
        else:
            print("❌ Docker Compose not found")
            return False
    except FileNotFoundError:
        print("❌ Docker Compose not found")
        return False
    
    return True


def install_dependencies():
    """Install Python dependencies"""
    print("\n📦 Installing Python dependencies...")
    
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'], 
                      check=True)
        print("✅ Dependencies installed")
        return True
    except subprocess.CalledProcessError:
        print("❌ Failed to install dependencies")
        return False


def start_infrastructure():
    """Start Docker infrastructure"""
    print("\n🐳 Starting infrastructure services...")
    
    try:
        # Start Docker services
        subprocess.run(['docker-compose', 'up', '-d'], check=True)
        
        print("⏳ Waiting for services to start...")
        time.sleep(10)
        
        # Check if services are running
        result = subprocess.run(['docker-compose', 'ps'], capture_output=True, text=True)
        if 'Up' in result.stdout:
            print("✅ Infrastructure services started")
            return True
        else:
            print("❌ Some services failed to start")
            return False
            
    except subprocess.CalledProcessError:
        print("❌ Failed to start infrastructure")
        return False


def setup_platform():
    """Setup the Aegis platform"""
    print("\n🚀 Setting up Aegis platform...")
    
    try:
        subprocess.run([sys.executable, 'main.py', 'setup'], check=True)
        print("✅ Platform setup complete")
        return True
    except subprocess.CalledProcessError:
        print("❌ Platform setup failed")
        return False


def check_env_file():
    """Check if .env file exists and has Twitter token"""
    env_file = Path('.env')
    
    if not env_file.exists():
        print("\n⚠️ .env file not found")
        print("📝 Creating .env file from template...")
        
        # Copy template
        template_file = Path('.env.template')
        if template_file.exists():
            with open(template_file, 'r') as src, open(env_file, 'w') as dst:
                dst.write(src.read())
            print("✅ .env file created from template")
        else:
            print("❌ .env.template not found")
            return False
    
    # Check for Twitter token
    with open(env_file, 'r') as f:
        content = f.read()
        if 'TWITTER_BEARER_TOKEN=your_twitter_bearer_token_here' in content:
            print("\n⚠️ Twitter Bearer Token not configured")
            print("📝 Please edit .env file and add your Twitter Bearer Token")
            print("   Get it from: https://developer.twitter.com/")
            return False
    
    print("✅ Configuration file ready")
    return True


def test_twitter():
    """Test Twitter connection"""
    print("\n🐦 Testing Twitter connection...")
    
    try:
        result = subprocess.run([sys.executable, 'main.py', 'test'], 
                              capture_output=True, text=True)
        
        if result.returncode == 0 and 'successful' in result.stdout:
            print("✅ Twitter connection successful")
            return True
        else:
            print("❌ Twitter connection failed")
            print("💡 Make sure your TWITTER_BEARER_TOKEN is correct in .env file")
            return False
            
    except subprocess.CalledProcessError:
        print("❌ Twitter test failed")
        return False


def main():
    """Main setup function"""
    print_banner()
    
    print("Welcome to Aegis VIP Threat Monitoring Platform!")
    print("This script will help you get started quickly.\n")
    
    # Check requirements
    if not check_requirements():
        print("\n❌ Requirements not met. Please install the required software.")
        return False
    
    # Install dependencies
    if not install_dependencies():
        print("\n❌ Failed to install dependencies.")
        return False
    
    # Start infrastructure
    if not start_infrastructure():
        print("\n❌ Failed to start infrastructure services.")
        return False
    
    # Setup platform
    if not setup_platform():
        print("\n❌ Failed to setup platform.")
        return False
    
    # Check environment configuration
    env_ready = check_env_file()
    
    if env_ready:
        # Test Twitter connection
        twitter_ready = test_twitter()
        
        if twitter_ready:
            print("\n🎉 Setup complete! Aegis is ready to use.")
            print("\n📝 Next steps:")
            print("   python main.py monitor --vip \"Celebrity Name\"")
            print("   python main.py status")
            return True
        else:
            print("\n⚠️ Setup mostly complete, but Twitter connection failed.")
            print("📝 Please check your Twitter Bearer Token in .env file")
            return False
    else:
        print("\n⚠️ Setup complete, but configuration needed.")
        print("📝 Please configure your .env file and run:")
        print("   python main.py test")
        return False


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n🛑 Setup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)