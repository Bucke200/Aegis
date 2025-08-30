"""
Pastebin scraper for monitoring leaked information and threats
"""
import asyncio
import re
from typing import Dict, Any, List, Optional, AsyncGenerator
from datetime import datetime, timedelta
from urllib.parse import urljoin, quote
import aiohttp
from bs4 import BeautifulSoup
from .base_scraper import BaseScraper, RateLimitConfig, ScrapingStatus
from messaging.schemas import SourceType
from shared.logging_config import logger


class PastebinScraper(BaseScraper):
    """Pastebin scraper for monitoring leaked information"""
    
    def __init__(self):
        # Pastebin rate limiting - be respectful
        rate_config = RateLimitConfig(
            requests_per_second=0.5,  # 1 request every 2 seconds
            requests_per_minute=20,
            requests_per_hour=500,
            delay_between_requests=2.0
        )
        
        super().__init__(
            source_type=SourceType.PASTEBIN,
            base_url='https://pastebin.com',
            rate_limit_config=rate_config
        )
        
        # Pastebin-specific configuration
        self.search_url = 'https://pastebin.com/search'
        self.archive_url = 'https://pastebin.com/archive'
        self.trends_url = 'https://pastebin.com/trends'
        
        # Content patterns for threat detection
        self.threat_patterns = [
            r'\b(?:password|pass|pwd)\s*[:=]\s*\S+',
            r'\b(?:email|mail)\s*[:=]\s*\S+@\S+',
            r'\b(?:phone|tel|mobile)\s*[:=]\s*[\d\-\+\(\)\s]+',
            r'\b(?:address|addr)\s*[:=]\s*.+',
            r'\b(?:ssn|social)\s*[:=]\s*\d{3}-?\d{2}-?\d{4}',
            r'\b(?:credit|card|cc)\s*[:=]\s*\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}',
            r'\b(?:api[_\s]?key|token|secret)\s*[:=]\s*\S+',
        ]
        
        # Compile patterns for efficiency
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.threat_patterns]
    
    async def search_content(self, 
                            query: str, 
                            limit: int = 100,
                            since: Optional[datetime] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Search Pastebin for content matching query"""
        
        try:
            # Note: Pastebin's search functionality is limited for free users
            # This implementation focuses on public archives and trends
            
            # Search in recent archives
            async for paste_data in self._search_archive(query, limit // 2, since):
                yield paste_data
            
            # Search in trending pastes
            async for paste_data in self._search_trends(query, limit // 2):
                yield paste_data
                
        except Exception as e:
            logger.error(f"Pastebin search failed for query '{query}': {e}")
            raise
    
    async def _search_archive(self, 
                             query: str, 
                             limit: int,
                             since: Optional[datetime]) -> AsyncGenerator[Dict[str, Any], None]:
        """Search in Pastebin archive"""
        
        try:
            # Get archive page
            response = await self._make_request(self.archive_url)
            
            if response.status != 200:
                logger.warning(f"Archive request failed with status {response.status}")
                return
            
            html_content = await response.text()
            soup = await self.parse_html(html_content, self.archive_url)
            
            # Find paste links in archive
            paste_links = []
            
            # Look for paste links (format: /XXXXXXXX)
            for link in soup.find_all('a', href=True):
                href = link['href']
                if re.match(r'^/[a-zA-Z0-9]{8}$', href):
                    paste_url = urljoin(self.base_url, href)
                    paste_links.append(paste_url)
            
            # Limit the number of pastes to check
            paste_links = paste_links[:limit]
            
            # Check each paste for query match
            for paste_url in paste_links:
                try:
                    paste_data = await self.scrape_url(paste_url)
                    
                    if paste_data and self._content_matches_query(paste_data, query):
                        # Check date filter
                        if since and paste_data.get('scraped_at'):
                            if paste_data['scraped_at'] < since:
                                continue
                        
                        yield paste_data
                
                except Exception as e:
                    logger.error(f"Error scraping paste {paste_url}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Archive search failed: {e}")
            raise
    
    async def _search_trends(self, 
                            query: str, 
                            limit: int) -> AsyncGenerator[Dict[str, Any], None]:
        """Search in trending pastes"""
        
        try:
            # Get trends page
            response = await self._make_request(self.trends_url)
            
            if response.status != 200:
                logger.warning(f"Trends request failed with status {response.status}")
                return
            
            html_content = await response.text()
            soup = await self.parse_html(html_content, self.trends_url)
            
            # Find trending paste links
            paste_links = []
            
            # Look for paste links in trends
            for link in soup.find_all('a', href=True):
                href = link['href']
                if re.match(r'^/[a-zA-Z0-9]{8}$', href):
                    paste_url = urljoin(self.base_url, href)
                    paste_links.append(paste_url)
            
            # Limit the number of pastes to check
            paste_links = paste_links[:limit]
            
            # Check each paste for query match
            for paste_url in paste_links:
                try:
                    paste_data = await self.scrape_url(paste_url)
                    
                    if paste_data and self._content_matches_query(paste_data, query):
                        yield paste_data
                
                except Exception as e:
                    logger.error(f"Error scraping trending paste {paste_url}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Trends search failed: {e}")
            raise
    
    async def scrape_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Scrape content from specific Pastebin URL"""
        
        try:
            # Make request to paste URL
            response = await self._make_request(url)
            
            if response.status != 200:
                logger.warning(f"Paste request failed with status {response.status} for {url}")
                return None
            
            html_content = await response.text()
            soup = await self.parse_html(html_content, url)
            
            # Extract paste data
            paste_data = await self._extract_paste_data(soup, url)
            
            if paste_data:
                # Add scraping metadata
                paste_data.update({
                    'scraped_at': datetime.utcnow(),
                    'page_hash': await self.calculate_content_hash(paste_data['content'])
                })
                
                # Analyze content for threats
                paste_data['threat_analysis'] = await self._analyze_content_threats(paste_data['content'])
            
            return paste_data
            
        except Exception as e:
            logger.error(f"Failed to scrape Pastebin URL {url}: {e}")
            return None
    
    async def _extract_paste_data(self, soup: BeautifulSoup, url: str) -> Optional[Dict[str, Any]]:
        """Extract paste data from parsed HTML"""
        
        try:
            # Extract paste ID from URL
            paste_id = url.split('/')[-1]
            
            # Find the paste content
            content_element = soup.find('textarea', {'id': 'paste_code'})
            if not content_element:
                # Try alternative selectors
                content_element = soup.find('div', {'class': 'source'})
                if not content_element:
                    content_element = soup.find('ol', {'class': 'bash'})
            
            if not content_element:
                logger.warning(f"Could not find paste content in {url}")
                return None
            
            # Extract content text
            if content_element.name == 'textarea':
                content = content_element.get_text()
            else:
                content = await self.extract_text_content(content_element)
            
            # Extract paste metadata
            title = "Untitled"
            title_element = soup.find('div', {'class': 'paste_box_line1'})
            if title_element:
                title_link = title_element.find('a')
                if title_link:
                    title = title_link.get_text().strip()
            
            # Extract author if available
            author = "Anonymous"
            author_element = soup.find('div', {'class': 'paste_box_line2'})
            if author_element:
                author_text = author_element.get_text()
                # Parse author from text like "By: username | Public | ..."
                if "By:" in author_text:
                    author_part = author_text.split("By:")[1].split("|")[0].strip()
                    if author_part and author_part != "a guest":
                        author = author_part
            
            # Extract date if available
            published_at = None
            date_element = soup.find('span', {'title': True})
            if date_element and 'CDT' in date_element.get('title', ''):
                try:
                    # Parse date from title attribute
                    date_str = date_element.get('title')
                    # This would need proper date parsing based on Pastebin's format
                    published_at = datetime.utcnow()  # Fallback to current time
                except Exception:
                    published_at = datetime.utcnow()
            
            # Count lines and words
            lines = content.split('\n')
            words = content.split()
            
            paste_data = {
                'url': url,
                'title': title,
                'content': content,
                'author': author,
                'published_at': published_at,
                'word_count': len(words),
                'line_count': len(lines),
                'language': self._detect_language(content),
                'paste_id': paste_id
            }
            
            return paste_data
            
        except Exception as e:
            logger.error(f"Failed to extract paste data from {url}: {e}")
            return None
    
    def _detect_language(self, content: str) -> Optional[str]:
        """Simple language detection based on content patterns"""
        
        # Check for common programming language patterns
        if re.search(r'\bdef\s+\w+\s*\(', content):
            return 'python'
        elif re.search(r'\bfunction\s+\w+\s*\(', content):
            return 'javascript'
        elif re.search(r'\bpublic\s+class\s+\w+', content):
            return 'java'
        elif re.search(r'#include\s*<', content):
            return 'c'
        elif re.search(r'\$\w+\s*=', content):
            return 'php'
        elif re.search(r'SELECT\s+.*\s+FROM', content, re.IGNORECASE):
            return 'sql'
        elif re.search(r'<html|<div|<span', content, re.IGNORECASE):
            return 'html'
        elif re.search(r'\{.*\}', content) and ':' in content:
            return 'json'
        
        return 'text'
    
    async def _analyze_content_threats(self, content: str) -> Dict[str, Any]:
        """Analyze content for potential threats and sensitive information"""
        
        threat_analysis = {
            'has_credentials': False,
            'has_personal_info': False,
            'has_financial_info': False,
            'has_api_keys': False,
            'threat_score': 0.0,
            'detected_patterns': []
        }
        
        try:
            # Check each threat pattern
            for i, pattern in enumerate(self.compiled_patterns):
                matches = pattern.findall(content)
                if matches:
                    pattern_name = self._get_pattern_name(i)
                    threat_analysis['detected_patterns'].append({
                        'pattern': pattern_name,
                        'count': len(matches),
                        'samples': matches[:3]  # First 3 matches as samples
                    })
                    
                    # Update threat flags
                    if 'password' in pattern_name or 'api' in pattern_name:
                        threat_analysis['has_credentials'] = True
                        threat_analysis['threat_score'] += 0.3
                    elif 'email' in pattern_name or 'phone' in pattern_name or 'address' in pattern_name:
                        threat_analysis['has_personal_info'] = True
                        threat_analysis['threat_score'] += 0.2
                    elif 'credit' in pattern_name or 'ssn' in pattern_name:
                        threat_analysis['has_financial_info'] = True
                        threat_analysis['threat_score'] += 0.4
                    elif 'api' in pattern_name or 'token' in pattern_name:
                        threat_analysis['has_api_keys'] = True
                        threat_analysis['threat_score'] += 0.3
            
            # Additional threat indicators
            threat_keywords = [
                'database dump', 'leaked', 'breach', 'hack', 'stolen',
                'confidential', 'internal', 'private', 'secret'
            ]
            
            content_lower = content.lower()
            for keyword in threat_keywords:
                if keyword in content_lower:
                    threat_analysis['threat_score'] += 0.1
                    threat_analysis['detected_patterns'].append({
                        'pattern': 'threat_keyword',
                        'keyword': keyword,
                        'count': content_lower.count(keyword)
                    })
            
            # Normalize threat score
            threat_analysis['threat_score'] = min(threat_analysis['threat_score'], 1.0)
            
        except Exception as e:
            logger.error(f"Error analyzing content threats: {e}")
        
        return threat_analysis
    
    def _get_pattern_name(self, pattern_index: int) -> str:
        """Get human-readable name for threat pattern"""
        pattern_names = [
            'password', 'email', 'phone', 'address', 'ssn',
            'credit_card', 'api_key'
        ]
        
        if pattern_index < len(pattern_names):
            return pattern_names[pattern_index]
        
        return f'pattern_{pattern_index}'
    
    def _content_matches_query(self, paste_data: Dict[str, Any], query: str) -> bool:
        """Check if paste content matches search query"""
        
        query_lower = query.lower()
        
        # Check title
        title = paste_data.get('title', '').lower()
        if query_lower in title:
            return True
        
        # Check content
        content = paste_data.get('content', '').lower()
        if query_lower in content:
            return True
        
        # Check author
        author = paste_data.get('author', '').lower()
        if query_lower in author:
            return True
        
        return False
    
    async def get_recent_pastes(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent public pastes from archive"""
        
        try:
            recent_pastes = []
            
            async for paste_data in self._search_archive('', limit, None):
                recent_pastes.append(paste_data)
                
                if len(recent_pastes) >= limit:
                    break
            
            return recent_pastes
            
        except Exception as e:
            logger.error(f"Failed to get recent pastes: {e}")
            return []
    
    async def monitor_sensitive_keywords(self, 
                                       keywords: List[str],
                                       vips: List[str] = None,
                                       interval: int = 600):  # 10 minutes
        """Monitor Pastebin for sensitive keywords"""
        
        # Add common threat-related keywords
        extended_keywords = keywords + [
            'leak', 'breach', 'hack', 'dump', 'stolen',
            'password', 'credential', 'database'
        ]
        
        # Add VIP names to keywords
        if vips:
            extended_keywords.extend(vips)
        
        await self.monitor_keywords(
            keywords=extended_keywords,
            vips=vips,
            interval=interval
        )


# Factory function for easy initialization
def create_pastebin_scraper() -> PastebinScraper:
    """Create Pastebin scraper"""
    return PastebinScraper()