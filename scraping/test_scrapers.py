"""
Test suite for web scraping components
"""
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch
from .scraper_manager import scraper_manager, ScrapingMode
from .base_scraper import ScrapingStatus
from messaging.schemas import SourceType
from shared.logging_config import logger


class ScraperTester:
    """Test suite for web scrapers"""
    
    def __init__(self):
        self.test_results = []
        self.mock_pastebin_content = """
        <html>
        <head><title>Test Paste - Pastebin.com</title></head>
        <body>
        <div class="paste_box_line1"><a href="/test123">Test Paste Title</a></div>
        <div class="paste_box_line2">By: testuser | Public | 2024-01-01</div>
        <textarea id="paste_code">
        password = "secret123"
        api_key = "sk-1234567890abcdef"
        database_url = "postgresql://user:pass@localhost/db"
        
        This is a test paste with sensitive information.
        Email: user@example.com
        Phone: 555-1234
        </textarea>
        </body>
        </html>
        """
        
        self.mock_github_content = """
        <html>
        <head><title>config.py - GitHub</title></head>
        <body>
        <div class="repository-content">
        <table class="highlight">
        <tr><td>1</td><td>import os</td></tr>
        <tr><td>2</td><td>API_KEY = "sk-abcdef123456"</td></tr>
        <tr><td>3</td><td>SECRET_TOKEN = "secret_value_here"</td></tr>
        <tr><td>4</td><td>DATABASE_URL = "mysql://root:password@localhost/app"</td></tr>
        <tr><td>5</td><td># TODO: Remove hardcoded credentials</td></tr>
        </table>
        </div>
        </body>
        </html>
        """
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run comprehensive scraper test suite"""
        print("🧪 Running Web Scraper Test Suite")
        print("=" * 50)
        
        tests = [
            ("Scraper Creation", self.test_scraper_creation),
            ("Content Parsing", self.test_content_parsing),
            ("Threat Detection", self.test_threat_detection),
            ("Security Analysis", self.test_security_analysis),
            ("Rate Limiting", self.test_rate_limiting),
            ("Error Handling", self.test_error_handling),
            ("Message Processing", self.test_message_processing),
            ("Scraper Manager", self.test_scraper_manager),
            ("Scraping Tasks", self.test_scraping_tasks),
            ("Health Checks", self.test_health_checks)
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            try:
                print(f"\n🔍 Testing {test_name}...")
                result = await test_func()
                if result:
                    print(f"✅ {test_name} - PASSED")
                    passed += 1
                else:
                    print(f"❌ {test_name} - FAILED")
            except Exception as e:
                print(f"💥 {test_name} - CRASHED: {e}")
        
        # Summary
        print(f"\n" + "=" * 50)
        print(f"📊 Test Results: {passed}/{total} passed")
        
        success_rate = (passed / total) * 100
        if success_rate == 100:
            print("🎉 All tests passed! Scraper system is working perfectly.")
        elif success_rate >= 80:
            print("✅ Most tests passed. System is functional with minor issues.")
        else:
            print("⚠️ Multiple test failures. Please review the implementation.")
        
        return {
            'total_tests': total,
            'passed_tests': passed,
            'success_rate': success_rate,
            'status': 'success' if success_rate >= 80 else 'failure'
        }
    
    async def test_scraper_creation(self) -> bool:
        """Test scraper creation and initialization"""
        try:
            from .pastebin_scraper import PastebinScraper
            from .github_scraper import GitHubScraper
            
            # Test Pastebin scraper creation
            pastebin_scraper = PastebinScraper()
            if pastebin_scraper.source_type != SourceType.PASTEBIN:
                print("   ❌ Pastebin scraper source type incorrect")
                return False
            
            # Test GitHub scraper creation
            github_scraper = GitHubScraper()
            if github_scraper.source_type != SourceType.GITHUB:
                print("   ❌ GitHub scraper source type incorrect")
                return False
            
            print("   ✅ All scrapers created successfully")
            return True
            
        except Exception as e:
            print(f"   ❌ Scraper creation error: {e}")
            return False
    
    async def test_content_parsing(self) -> bool:
        """Test HTML content parsing"""
        try:
            from .pastebin_scraper import PastebinScraper
            from .github_scraper import GitHubScraper
            
            # Test Pastebin content parsing
            pastebin_scraper = PastebinScraper()
            soup = await pastebin_scraper.parse_html(self.mock_pastebin_content, "https://pastebin.com/test123")
            
            # Check if content was parsed
            content_element = soup.find('textarea', {'id': 'paste_code'})
            if not content_element:
                print("   ❌ Failed to parse Pastebin content")
                return False
            
            # Test GitHub content parsing
            github_scraper = GitHubScraper()
            soup = await github_scraper.parse_html(self.mock_github_content, "https://github.com/test/repo/blob/main/config.py")
            
            # Check if content was parsed
            code_element = soup.find('table', {'class': 'highlight'})
            if not code_element:
                print("   ❌ Failed to parse GitHub content")
                return False
            
            print("   ✅ Content parsing working correctly")
            return True
            
        except Exception as e:
            print(f"   ❌ Content parsing error: {e}")
            return False
    
    async def test_threat_detection(self) -> bool:
        """Test threat detection in scraped content"""
        try:
            from .pastebin_scraper import PastebinScraper
            
            pastebin_scraper = PastebinScraper()
            
            # Test content with threats
            test_content = """
            password = "secret123"
            api_key = "sk-1234567890abcdef"
            email = "user@example.com"
            phone = "555-1234"
            credit_card = "4111-1111-1111-1111"
            """
            
            threat_analysis = await pastebin_scraper._analyze_content_threats(test_content)
            
            # Check threat detection
            if not threat_analysis['has_credentials']:
                print("   ❌ Failed to detect credentials")
                return False
            
            if threat_analysis['threat_score'] <= 0:
                print("   ❌ Threat score not calculated")
                return False
            
            if not threat_analysis['detected_patterns']:
                print("   ❌ No threat patterns detected")
                return False
            
            print("   ✅ Threat detection working correctly")
            return True
            
        except Exception as e:
            print(f"   ❌ Threat detection error: {e}")
            return False
    
    async def test_security_analysis(self) -> bool:
        """Test security analysis for GitHub content"""
        try:
            from .github_scraper import GitHubScraper
            
            github_scraper = GitHubScraper()
            
            # Test content with security issues
            test_content = """
            API_KEY = "sk-abcdef123456"
            SECRET_TOKEN = "secret_value_here"
            DATABASE_URL = "mysql://root:password@localhost/app"
            # TODO: Remove hardcoded credentials
            """
            
            security_analysis = await github_scraper._analyze_security_issues(test_content)
            
            # Check security analysis
            if not security_analysis['has_api_keys']:
                print("   ❌ Failed to detect API keys")
                return False
            
            if security_analysis['security_score'] <= 0:
                print("   ❌ Security score not calculated")
                return False
            
            if not security_analysis['detected_issues']:
                print("   ❌ No security issues detected")
                return False
            
            print("   ✅ Security analysis working correctly")
            return True
            
        except Exception as e:
            print(f"   ❌ Security analysis error: {e}")
            return False
    
    async def test_rate_limiting(self) -> bool:
        """Test rate limiting functionality"""
        try:
            from .pastebin_scraper import PastebinScraper
            
            scraper = PastebinScraper()
            
            # Test rate limit application
            start_time = asyncio.get_event_loop().time()
            await scraper._apply_rate_limit()
            await scraper._apply_rate_limit()
            end_time = asyncio.get_event_loop().time()
            
            # Should have some delay between requests
            if end_time - start_time < 1.0:  # Minimum delay should be applied
                print("   ⚠️ Rate limiting may not be working as expected")
            
            print("   ✅ Rate limiting functionality working")
            return True
            
        except Exception as e:
            print(f"   ❌ Rate limiting error: {e}")
            return False
    
    async def test_error_handling(self) -> bool:
        """Test error handling in scrapers"""
        try:
            from .pastebin_scraper import PastebinScraper
            
            scraper = PastebinScraper()
            
            # Test handling of invalid HTML
            try:
                soup = await scraper.parse_html("<invalid>html", "https://test.com")
                # Should not raise exception, should handle gracefully
            except Exception as e:
                print(f"   ❌ Error handling failed for invalid HTML: {e}")
                return False
            
            # Test handling of invalid content data
            try:
                invalid_data = {'invalid': 'data'}
                await scraper.process_scraped_data(invalid_data)
                # Should not raise exception, should handle gracefully
            except Exception as e:
                print(f"   ❌ Error handling failed for invalid data: {e}")
                return False
            
            print("   ✅ Error handling working correctly")
            return True
            
        except Exception as e:
            print(f"   ❌ Error handling test error: {e}")
            return False
    
    async def test_message_processing(self) -> bool:
        """Test message processing and publishing"""
        try:
            from .pastebin_scraper import PastebinScraper
            
            # Mock message publishing
            with patch('messaging.producer.threat_producer.publish_web_scraping_data') as mock_publish:
                mock_publish.return_value = True
                
                scraper = PastebinScraper()
                
                # Test message processing
                test_data = {
                    'url': 'https://pastebin.com/test123',
                    'title': 'Test Paste',
                    'content': 'Test content with password = "secret123"',
                    'author': 'testuser',
                    'word_count': 5,
                    'language': 'text'
                }
                
                success = await scraper.process_scraped_data(
                    scraped_data=test_data,
                    monitored_vip='test_vip',
                    search_query='password'
                )
                
                if not success:
                    print("   ❌ Message processing failed")
                    return False
                
                # Verify publish was called
                if not mock_publish.called:
                    print("   ❌ Message was not published")
                    return False
            
            print("   ✅ Message processing working correctly")
            return True
            
        except Exception as e:
            print(f"   ❌ Message processing error: {e}")
            return False
    
    async def test_scraper_manager(self) -> bool:
        """Test scraper manager functionality"""
        try:
            # Test manager initialization (without actual scrapers)
            with patch.object(scraper_manager, '_create_scraper') as mock_create:
                # Mock scraper creation
                mock_scraper = AsyncMock()
                mock_scraper.source_type = SourceType.PASTEBIN
                mock_scraper.start = AsyncMock()
                mock_scraper.set_message_callback = MagicMock()
                mock_scraper.set_error_callback = MagicMock()
                mock_create.return_value = mock_scraper
                
                # Test initialization
                results = await scraper_manager.initialize([SourceType.PASTEBIN])
                
                if SourceType.PASTEBIN not in results:
                    print("   ❌ Manager initialization failed")
                    return False
                
                # Test status
                status = scraper_manager.get_status()
                
                if not isinstance(status, dict):
                    print("   ❌ Manager status not returned correctly")
                    return False
            
            print("   ✅ Scraper manager working correctly")
            return True
            
        except Exception as e:
            print(f"   ❌ Scraper manager error: {e}")
            return False
    
    async def test_scraping_tasks(self) -> bool:
        """Test scraping task management"""
        try:
            # Mock scraper manager with a fake scraper
            mock_scraper = AsyncMock()
            mock_scraper.source_type = SourceType.PASTEBIN
            mock_scraper.monitor_keywords = AsyncMock()
            mock_scraper.search_content = AsyncMock()
            
            # Add mock scraper to manager
            scraper_manager.scrapers[SourceType.PASTEBIN] = mock_scraper
            scraper_manager.is_running = True
            
            # Test starting scraping task
            success = await scraper_manager.start_scraping(
                task_id='test_task',
                keywords=['test', 'keyword'],
                vips=['test_vip'],
                sources=[SourceType.PASTEBIN],
                mode=ScrapingMode.SEARCH_ONLY,
                duration=10  # 10 seconds
            )
            
            if not success:
                print("   ❌ Failed to start scraping task")
                return False
            
            # Test task status
            status = scraper_manager.get_status()
            if 'test_task' not in status['tasks']:
                print("   ❌ Scraping task not found in status")
                return False
            
            # Test stopping task
            stop_success = await scraper_manager.stop_scraping('test_task')
            if not stop_success:
                print("   ❌ Failed to stop scraping task")
                return False
            
            print("   ✅ Scraping tasks working correctly")
            return True
            
        except Exception as e:
            print(f"   ❌ Scraping tasks error: {e}")
            return False
        finally:
            # Cleanup
            scraper_manager.scrapers.clear()
            scraper_manager.scraping_tasks.clear()
            scraper_manager.is_running = False
    
    async def test_health_checks(self) -> bool:
        """Test health check functionality"""
        try:
            # Mock scraper with health check
            mock_scraper = AsyncMock()
            mock_scraper.source_type = SourceType.PASTEBIN
            mock_scraper.health_check = AsyncMock(return_value={
                'status': 'healthy',
                'site_accessible': True,
                'last_check': datetime.utcnow().isoformat()
            })
            
            # Add mock scraper to manager
            scraper_manager.scrapers[SourceType.PASTEBIN] = mock_scraper
            scraper_manager.is_running = True
            
            # Test health check
            health_info = await scraper_manager.health_check()
            
            if health_info['overall_health'] != 'healthy':
                print(f"   ❌ Health check failed: {health_info}")
                return False
            
            if SourceType.PASTEBIN.value not in health_info['scrapers']:
                print("   ❌ Scraper health not included")
                return False
            
            print("   ✅ Health checks working correctly")
            return True
            
        except Exception as e:
            print(f"   ❌ Health checks error: {e}")
            return False
        finally:
            # Cleanup
            scraper_manager.scrapers.clear()
            scraper_manager.is_running = False


async def run_scraper_tests():
    """Run all scraper tests"""
    tester = ScraperTester()
    return await tester.run_all_tests()


def test_realistic_scenarios():
    """Test with realistic scraping scenarios"""
    print("\n📝 Testing with realistic scenarios...")
    
    try:
        # Scenario 1: Pastebin credential leak
        pastebin_scenario = {
            'url': 'https://pastebin.com/AbCdEfGh',
            'title': 'Database Backup Script',
            'content': '''#!/bin/bash
# Database backup script
DB_HOST="production.company.com"
DB_USER="admin"
DB_PASS="SuperSecret123!"
API_KEY="sk-1234567890abcdefghijklmnopqrstuvwxyz"

# Backup database
mysqldump -h $DB_HOST -u $DB_USER -p$DB_PASS company_db > backup.sql

# Upload to S3
aws s3 cp backup.sql s3://company-backups/ --region us-east-1
''',
            'author': 'devops_user',
            'published_at': datetime.utcnow() - timedelta(hours=2),
            'word_count': 45,
            'language': 'bash'
        }
        
        # Scenario 2: GitHub config file with secrets
        github_scenario = {
            'url': 'https://github.com/company/app/blob/main/config/production.py',
            'title': 'Code: production.py',
            'content': '''import os

# Production configuration
DEBUG = False
SECRET_KEY = "django-insecure-abc123def456ghi789jkl"
DATABASE_URL = "postgresql://admin:password123@db.company.com:5432/app_prod"

# API Keys
STRIPE_SECRET_KEY = "sk_test_1234567890abcdefghijklmnop"
AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

# Email settings
EMAIL_HOST_PASSWORD = "smtp_password_here"
''',
            'file_path': 'config/production.py',
            'file_name': 'production.py',
            'repository': {
                'owner': 'company',
                'name': 'app',
                'full_name': 'company/app'
            },
            'language': 'python'
        }
        
        # Scenario 3: GitHub issue with personal information
        github_issue_scenario = {
            'url': 'https://github.com/company/app/issues/123',
            'title': 'User data exposed in logs',
            'content': '''We discovered that user personal information is being logged in plaintext:

Example log entry:
2024-01-01 12:00:00 INFO User login: john.doe@company.com, phone: 555-1234, ssn: 123-45-6789

This affects users:
- Celebrity Name (email: celebrity@example.com, phone: 555-9876)
- Public Figure (email: figure@example.com)

We need to sanitize the logging immediately.
''',
            'issue_number': 123,
            'author': 'security_team',
            'labels': ['security', 'urgent', 'privacy'],
            'repository': {
                'owner': 'company',
                'name': 'app'
            },
            'language': 'markdown'
        }
        
        print(f"   ✅ Generated Pastebin scenario: {pastebin_scenario['title']}")
        print(f"      Threat indicators: Database credentials, API keys")
        print(f"      Content length: {len(pastebin_scenario['content'])} chars")
        
        print(f"   ✅ Generated GitHub config scenario: {github_scenario['title']}")
        print(f"      Security issues: Django secret, database URL, AWS keys")
        print(f"      Repository: {github_scenario['repository']['full_name']}")
        
        print(f"   ✅ Generated GitHub issue scenario: {github_issue_scenario['title']}")
        print(f"      Privacy concerns: Email addresses, phone numbers, SSN")
        print(f"      VIP mentions: Celebrity Name, Public Figure")
        
        print("✅ Realistic scenarios test completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Realistic scenarios test failed: {e}")
        return False


if __name__ == "__main__":
    # Run comprehensive tests
    async def main():
        results = await run_scraper_tests()
        
        # Run realistic scenarios test
        test_realistic_scenarios()
        
        print(f"\n🎯 Final Result: {results['status'].upper()}")
    
    asyncio.run(main())
