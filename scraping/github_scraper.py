"""
GitHub scraper for monitoring code repositories and issues
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
from shared.config import settings
from shared.logging_config import logger


class GitHubScraper(BaseScraper):
    """GitHub scraper for monitoring repositories and code"""
    
    def __init__(self, github_token: Optional[str] = None):
        # GitHub rate limiting - be respectful
        rate_config = RateLimitConfig(
            requests_per_second=0.5,  # 1 request every 2 seconds
            requests_per_minute=30,
            requests_per_hour=1000,
            delay_between_requests=2.0
        )
        
        super().__init__(
            source_type=SourceType.GITHUB,
            base_url='https://github.com',
            rate_limit_config=rate_config
        )
        
        # GitHub-specific configuration
        self.api_base_url = 'https://api.github.com'
        self.search_url = 'https://github.com/search'
        self.github_token = github_token or settings.github_token
        
        # Search types
        self.search_types = ['repositories', 'code', 'issues', 'users']
        
        # Sensitive content patterns
        self.sensitive_patterns = [
            r'(?i)\b(?:password|pass|pwd)\s*[:=]\s*["\']?[^"\'\s]+["\']?',
            r'(?i)\b(?:api[_\s]?key|apikey)\s*[:=]\s*["\']?[^"\'\s]+["\']?',
            r'(?i)\b(?:secret|token)\s*[:=]\s*["\']?[^"\'\s]+["\']?',
            r'(?i)\b(?:private[_\s]?key|privatekey)\s*[:=]\s*["\']?[^"\'\s]+["\']?',
            r'(?i)\b(?:access[_\s]?token|accesstoken)\s*[:=]\s*["\']?[^"\'\s]+["\']?',
            r'(?i)-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----',
            r'(?i)\b(?:aws[_\s]?(?:access[_\s]?)?key|aws[_\s]?secret)\s*[:=]\s*["\']?[^"\'\s]+["\']?',
            r'(?i)\b(?:database[_\s]?url|db[_\s]?url)\s*[:=]\s*["\']?[^"\'\s]+["\']?',
        ]
        
        # Compile patterns for efficiency
        self.compiled_patterns = [re.compile(pattern) for pattern in self.sensitive_patterns]
    
    async def _initialize_session(self):
        """Initialize HTTP session with GitHub-specific headers"""
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'application/vnd.github.v3+json',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        
        # Add authentication if token is available
        if self.github_token:
            headers['Authorization'] = f'token {self.github_token}'
        
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        
        self.session = aiohttp.ClientSession(
            headers=headers,
            timeout=timeout,
            connector=aiohttp.TCPConnector(limit=10)
        )
    
    async def search_content(self, 
                            query: str, 
                            limit: int = 100,
                            since: Optional[datetime] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Search GitHub for content matching query"""
        
        try:
            # Search in different categories
            search_types = ['code', 'repositories', 'issues']
            
            for search_type in search_types:
                async for result in self._search_github(query, search_type, limit // len(search_types), since):
                    yield result
                    
        except Exception as e:
            logger.error(f"GitHub search failed for query '{query}': {e}")
            raise
    
    async def _search_github(self, 
                            query: str, 
                            search_type: str,
                            limit: int,
                            since: Optional[datetime]) -> AsyncGenerator[Dict[str, Any], None]:
        """Search GitHub using web interface or API"""
        
        try:
            if self.github_token:
                # Use API if token is available
                async for result in self._search_api(query, search_type, limit, since):
                    yield result
            else:
                # Use web scraping
                async for result in self._search_web(query, search_type, limit, since):
                    yield result
                    
        except Exception as e:
            logger.error(f"GitHub {search_type} search failed: {e}")
            raise
    
    async def _search_api(self, 
                         query: str, 
                         search_type: str,
                         limit: int,
                         since: Optional[datetime]) -> AsyncGenerator[Dict[str, Any], None]:
        """Search using GitHub API"""
        
        try:
            # Construct API URL
            api_url = f"{self.api_base_url}/search/{search_type}"
            
            # Prepare query parameters
            params = {
                'q': query,
                'per_page': min(limit, 100),  # GitHub API limit
                'sort': 'updated',
                'order': 'desc'
            }
            
            # Add date filter if specified
            if since:
                date_str = since.strftime('%Y-%m-%d')
                params['q'] += f' created:>={date_str}'
            
            # Make API request
            response = await self._make_request(api_url, params=params)
            
            if response.status != 200:
                logger.warning(f"GitHub API request failed with status {response.status}")
                return
            
            data = await response.json()
            items = data.get('items', [])
            
            # Process each result
            for item in items:
                try:
                    result_data = await self._process_api_result(item, search_type)
                    if result_data:
                        yield result_data
                        
                except Exception as e:
                    logger.error(f"Error processing API result: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"GitHub API search failed: {e}")
            raise
    
    async def _search_web(self, 
                         query: str, 
                         search_type: str,
                         limit: int,
                         since: Optional[datetime]) -> AsyncGenerator[Dict[str, Any], None]:
        """Search using GitHub web interface"""
        
        try:
            # Construct search URL
            search_url = f"{self.search_url}?q={quote(query)}&type={search_type}"
            
            # Make request
            response = await self._make_request(search_url)
            
            if response.status != 200:
                logger.warning(f"GitHub web search failed with status {response.status}")
                return
            
            html_content = await response.text()
            soup = await self.parse_html(html_content, search_url)
            
            # Extract search results
            results = await self._extract_web_results(soup, search_type)
            
            # Process each result
            count = 0
            for result_url in results:
                if count >= limit:
                    break
                
                try:
                    result_data = await self.scrape_url(result_url)
                    if result_data:
                        yield result_data
                        count += 1
                        
                except Exception as e:
                    logger.error(f"Error scraping result {result_url}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"GitHub web search failed: {e}")
            raise
    
    async def _extract_web_results(self, soup: BeautifulSoup, search_type: str) -> List[str]:
        """Extract result URLs from search page"""
        
        result_urls = []
        
        try:
            if search_type == 'repositories':
                # Find repository links
                for link in soup.find_all('a', {'data-testid': 'results-list'}):
                    href = link.get('href')
                    if href and href.startswith('/'):
                        result_urls.append(urljoin(self.base_url, href))
            
            elif search_type == 'code':
                # Find code file links
                for link in soup.find_all('a', href=True):
                    href = link.get('href')
                    if href and '/blob/' in href:
                        result_urls.append(urljoin(self.base_url, href))
            
            elif search_type == 'issues':
                # Find issue links
                for link in soup.find_all('a', href=True):
                    href = link.get('href')
                    if href and '/issues/' in href:
                        result_urls.append(urljoin(self.base_url, href))
            
            # Remove duplicates
            result_urls = list(set(result_urls))
            
        except Exception as e:
            logger.error(f"Error extracting web results: {e}")
        
        return result_urls
    
    async def scrape_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Scrape content from specific GitHub URL"""
        
        try:
            # Make request
            response = await self._make_request(url)
            
            if response.status != 200:
                logger.warning(f"GitHub URL request failed with status {response.status} for {url}")
                return None
            
            html_content = await response.text()
            soup = await self.parse_html(html_content, url)
            
            # Determine content type and extract accordingly
            if '/blob/' in url:
                # Code file
                content_data = await self._extract_code_file(soup, url)
            elif '/issues/' in url:
                # Issue
                content_data = await self._extract_issue(soup, url)
            elif '/tree/' in url or url.count('/') == 4:
                # Repository
                content_data = await self._extract_repository(soup, url)
            else:
                # Generic content
                content_data = await self._extract_generic_content(soup, url)
            
            if content_data:
                # Add scraping metadata
                content_data.update({
                    'scraped_at': datetime.utcnow(),
                    'page_hash': await self.calculate_content_hash(content_data['content'])
                })
                
                # Analyze for sensitive content
                content_data['security_analysis'] = await self._analyze_security_issues(content_data['content'])
            
            return content_data
            
        except Exception as e:
            logger.error(f"Failed to scrape GitHub URL {url}: {e}")
            return None
    
    async def _extract_code_file(self, soup: BeautifulSoup, url: str) -> Optional[Dict[str, Any]]:
        """Extract code file content"""
        
        try:
            # Find code content
            code_element = soup.find('table', {'class': 'highlight'})
            if not code_element:
                code_element = soup.find('div', {'class': 'blob-wrapper'})
            
            if not code_element:
                logger.warning(f"Could not find code content in {url}")
                return None
            
            # Extract code text
            code_content = await self.extract_text_content(code_element)
            
            # Extract file metadata
            file_path = self._extract_file_path(url)
            file_name = file_path.split('/')[-1] if file_path else 'unknown'
            
            # Extract repository info
            repo_info = self._extract_repo_info(url)
            
            # Extract commit info if available
            commit_info = await self._extract_commit_info(soup)
            
            content_data = {
                'url': url,
                'title': f"Code: {file_name}",
                'content': code_content,
                'file_path': file_path,
                'file_name': file_name,
                'repository': repo_info,
                'commit_info': commit_info,
                'word_count': len(code_content.split()),
                'line_count': len(code_content.split('\n')),
                'language': self._detect_language_from_extension(file_name)
            }
            
            return content_data
            
        except Exception as e:
            logger.error(f"Failed to extract code file from {url}: {e}")
            return None
    
    async def _extract_issue(self, soup: BeautifulSoup, url: str) -> Optional[Dict[str, Any]]:
        """Extract GitHub issue content"""
        
        try:
            # Find issue title
            title_element = soup.find('h1', {'class': 'gh-header-title'})
            title = title_element.get_text().strip() if title_element else 'Unknown Issue'
            
            # Find issue body
            body_element = soup.find('div', {'class': 'comment-body'})
            if not body_element:
                body_element = soup.find('td', {'class': 'comment-body'})
            
            content = ""
            if body_element:
                content = await self.extract_text_content(body_element)
            
            # Extract issue metadata
            repo_info = self._extract_repo_info(url)
            issue_number = self._extract_issue_number(url)
            
            # Extract labels and status
            labels = []
            label_elements = soup.find_all('a', {'class': 'IssueLabel'})
            for label_elem in label_elements:
                labels.append(label_elem.get_text().strip())
            
            # Extract author
            author = "Unknown"
            author_element = soup.find('a', {'class': 'author'})
            if author_element:
                author = author_element.get_text().strip()
            
            content_data = {
                'url': url,
                'title': title,
                'content': content,
                'repository': repo_info,
                'issue_number': issue_number,
                'author': author,
                'labels': labels,
                'word_count': len(content.split()),
                'language': 'markdown'
            }
            
            return content_data
            
        except Exception as e:
            logger.error(f"Failed to extract issue from {url}: {e}")
            return None
    
    async def _extract_repository(self, soup: BeautifulSoup, url: str) -> Optional[Dict[str, Any]]:
        """Extract repository information"""
        
        try:
            # Find repository description
            desc_element = soup.find('p', {'class': 'f4'})
            description = desc_element.get_text().strip() if desc_element else ""
            
            # Find README content
            readme_element = soup.find('div', {'class': 'Box-body'})
            readme_content = ""
            if readme_element:
                readme_content = await self.extract_text_content(readme_element)
            
            # Extract repository metadata
            repo_info = self._extract_repo_info(url)
            
            # Combine description and README
            full_content = f"{description}\n\n{readme_content}".strip()
            
            content_data = {
                'url': url,
                'title': f"Repository: {repo_info.get('name', 'Unknown')}",
                'content': full_content,
                'description': description,
                'readme_content': readme_content,
                'repository': repo_info,
                'word_count': len(full_content.split()),
                'language': 'markdown'
            }
            
            return content_data
            
        except Exception as e:
            logger.error(f"Failed to extract repository from {url}: {e}")
            return None
    
    async def _extract_generic_content(self, soup: BeautifulSoup, url: str) -> Optional[Dict[str, Any]]:
        """Extract generic content from GitHub page"""
        
        try:
            # Extract title
            title_element = soup.find('title')
            title = title_element.get_text().strip() if title_element else 'GitHub Content'
            
            # Extract main content
            main_element = soup.find('main')
            if not main_element:
                main_element = soup.find('div', {'class': 'application-main'})
            
            content = ""
            if main_element:
                content = await self.extract_text_content(main_element)
            
            content_data = {
                'url': url,
                'title': title,
                'content': content,
                'word_count': len(content.split()),
                'language': 'text'
            }
            
            return content_data
            
        except Exception as e:
            logger.error(f"Failed to extract generic content from {url}: {e}")
            return None
    
    def _extract_repo_info(self, url: str) -> Dict[str, str]:
        """Extract repository information from URL"""
        
        try:
            # Parse URL to get owner and repo name
            # Format: https://github.com/owner/repo/...
            parts = url.replace('https://github.com/', '').split('/')
            
            if len(parts) >= 2:
                return {
                    'owner': parts[0],
                    'name': parts[1],
                    'full_name': f"{parts[0]}/{parts[1]}"
                }
        except Exception:
            pass
        
        return {'owner': 'unknown', 'name': 'unknown', 'full_name': 'unknown/unknown'}
    
    def _extract_file_path(self, url: str) -> str:
        """Extract file path from GitHub blob URL"""
        
        try:
            # Format: https://github.com/owner/repo/blob/branch/path/to/file
            if '/blob/' in url:
                blob_part = url.split('/blob/')[1]
                # Remove branch name (first part after blob)
                path_parts = blob_part.split('/')[1:]
                return '/'.join(path_parts)
        except Exception:
            pass
        
        return 'unknown'
    
    def _extract_issue_number(self, url: str) -> Optional[int]:
        """Extract issue number from GitHub issue URL"""
        
        try:
            # Format: https://github.com/owner/repo/issues/123
            if '/issues/' in url:
                issue_part = url.split('/issues/')[1]
                issue_number = issue_part.split('/')[0]
                return int(issue_number)
        except Exception:
            pass
        
        return None
    
    async def _extract_commit_info(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract commit information from code page"""
        
        commit_info = {}
        
        try:
            # Find commit link
            commit_link = soup.find('a', {'class': 'commit-tease-sha'})
            if commit_link:
                commit_info['sha'] = commit_link.get_text().strip()
                commit_info['url'] = urljoin(self.base_url, commit_link.get('href', ''))
            
            # Find commit message
            commit_msg = soup.find('a', {'class': 'Link--primary'})
            if commit_msg:
                commit_info['message'] = commit_msg.get_text().strip()
        
        except Exception as e:
            logger.error(f"Error extracting commit info: {e}")
        
        return commit_info
    
    def _detect_language_from_extension(self, filename: str) -> str:
        """Detect programming language from file extension"""
        
        extension_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.java': 'java',
            '.c': 'c',
            '.cpp': 'cpp',
            '.h': 'c',
            '.php': 'php',
            '.rb': 'ruby',
            '.go': 'go',
            '.rs': 'rust',
            '.sh': 'shell',
            '.sql': 'sql',
            '.html': 'html',
            '.css': 'css',
            '.json': 'json',
            '.xml': 'xml',
            '.yml': 'yaml',
            '.yaml': 'yaml',
            '.md': 'markdown',
            '.txt': 'text'
        }
        
        for ext, lang in extension_map.items():
            if filename.lower().endswith(ext):
                return lang
        
        return 'text'
    
    async def _analyze_security_issues(self, content: str) -> Dict[str, Any]:
        """Analyze content for security issues and sensitive information"""
        
        security_analysis = {
            'has_credentials': False,
            'has_api_keys': False,
            'has_private_keys': False,
            'has_database_urls': False,
            'security_score': 0.0,
            'detected_issues': []
        }
        
        try:
            # Check each sensitive pattern
            for i, pattern in enumerate(self.compiled_patterns):
                matches = pattern.findall(content)
                if matches:
                    issue_type = self._get_security_issue_type(i)
                    security_analysis['detected_issues'].append({
                        'type': issue_type,
                        'count': len(matches),
                        'samples': [match[:50] + '...' if len(match) > 50 else match for match in matches[:3]]
                    })
                    
                    # Update security flags and score
                    if 'password' in issue_type or 'credential' in issue_type:
                        security_analysis['has_credentials'] = True
                        security_analysis['security_score'] += 0.4
                    elif 'api_key' in issue_type or 'token' in issue_type:
                        security_analysis['has_api_keys'] = True
                        security_analysis['security_score'] += 0.3
                    elif 'private_key' in issue_type:
                        security_analysis['has_private_keys'] = True
                        security_analysis['security_score'] += 0.5
                    elif 'database' in issue_type:
                        security_analysis['has_database_urls'] = True
                        security_analysis['security_score'] += 0.3
            
            # Additional security checks
            security_keywords = [
                'hardcoded', 'todo: remove', 'temporary', 'debug',
                'backdoor', 'vulnerability', 'exploit'
            ]
            
            content_lower = content.lower()
            for keyword in security_keywords:
                if keyword in content_lower:
                    security_analysis['security_score'] += 0.1
                    security_analysis['detected_issues'].append({
                        'type': 'security_keyword',
                        'keyword': keyword,
                        'count': content_lower.count(keyword)
                    })
            
            # Normalize security score
            security_analysis['security_score'] = min(security_analysis['security_score'], 1.0)
            
        except Exception as e:
            logger.error(f"Error analyzing security issues: {e}")
        
        return security_analysis
    
    def _get_security_issue_type(self, pattern_index: int) -> str:
        """Get security issue type name"""
        issue_types = [
            'password', 'api_key', 'secret_token', 'private_key',
            'access_token', 'private_key_pem', 'aws_key', 'database_url'
        ]
        
        if pattern_index < len(issue_types):
            return issue_types[pattern_index]
        
        return f'security_issue_{pattern_index}'
    
    async def _process_api_result(self, item: Dict[str, Any], search_type: str) -> Optional[Dict[str, Any]]:
        """Process API search result item"""
        
        try:
            if search_type == 'repositories':
                return {
                    'url': item.get('html_url'),
                    'title': f"Repository: {item.get('full_name')}",
                    'content': item.get('description', ''),
                    'repository': {
                        'name': item.get('name'),
                        'owner': item.get('owner', {}).get('login'),
                        'full_name': item.get('full_name')
                    },
                    'language': item.get('language', 'unknown'),
                    'stars': item.get('stargazers_count', 0),
                    'forks': item.get('forks_count', 0)
                }
            
            elif search_type == 'code':
                return {
                    'url': item.get('html_url'),
                    'title': f"Code: {item.get('name')}",
                    'content': item.get('text_matches', [{}])[0].get('fragment', ''),
                    'file_path': item.get('path'),
                    'file_name': item.get('name'),
                    'repository': {
                        'name': item.get('repository', {}).get('name'),
                        'owner': item.get('repository', {}).get('owner', {}).get('login'),
                        'full_name': item.get('repository', {}).get('full_name')
                    },
                    'language': self._detect_language_from_extension(item.get('name', ''))
                }
            
            elif search_type == 'issues':
                return {
                    'url': item.get('html_url'),
                    'title': item.get('title'),
                    'content': item.get('body', ''),
                    'issue_number': item.get('number'),
                    'state': item.get('state'),
                    'author': item.get('user', {}).get('login'),
                    'repository': {
                        'name': item.get('repository_url', '').split('/')[-1],
                        'owner': item.get('repository_url', '').split('/')[-2],
                    },
                    'language': 'markdown'
                }
            
        except Exception as e:
            logger.error(f"Error processing API result: {e}")
        
        return None


# Factory function for easy initialization
def create_github_scraper(github_token: Optional[str] = None) -> GitHubScraper:
    """Create GitHub scraper"""
    return GitHubScraper(github_token)