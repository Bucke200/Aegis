"""
File storage service for Aegis platform
Supports local filesystem and S3-compatible storage
"""
import os
import shutil
import hashlib
import mimetypes
from pathlib import Path
from typing import Optional, Dict, Any, BinaryIO, Union
from datetime import datetime, timedelta
import uuid
from urllib.parse import urlparse

from shared.config import settings
from shared.logging_config import logger


class FileStorageService:
    """File storage service with local and cloud support"""
    
    def __init__(self):
        self.storage_path = Path(settings.storage_path)
        self.max_file_size = self._parse_file_size(settings.max_file_size)
        self._ensure_directories()
    
    def _parse_file_size(self, size_str: str) -> int:
        """Parse file size string (e.g., '50MB') to bytes"""
        size_str = size_str.upper().strip()
        
        multipliers = {
            'B': 1,
            'KB': 1024,
            'MB': 1024 ** 2,
            'GB': 1024 ** 3
        }
        
        for suffix, multiplier in multipliers.items():
            if size_str.endswith(suffix):
                try:
                    number = float(size_str[:-len(suffix)])
                    return int(number * multiplier)
                except ValueError:
                    pass
        
        # Default to 50MB if parsing fails
        return 50 * 1024 ** 2
    
    def _ensure_directories(self):
        """Create storage directories if they don't exist"""
        directories = [
            self.storage_path,
            self.storage_path / "screenshots",
            self.storage_path / "media",
            self.storage_path / "evidence",
            self.storage_path / "temp"
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured directory exists: {directory}")
    
    def _generate_file_path(self, file_type: str, file_extension: str = None) -> Path:
        """Generate a unique file path"""
        # Create date-based subdirectory
        date_dir = datetime.utcnow().strftime("%Y/%m/%d")
        base_dir = self.storage_path / file_type / date_dir
        base_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        file_id = str(uuid.uuid4())
        if file_extension:
            filename = f"{file_id}.{file_extension.lstrip('.')}"
        else:
            filename = file_id
        
        return base_dir / filename
    
    def _get_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file"""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    
    def _get_file_info(self, file_path: Path) -> Dict[str, Any]:
        """Get file metadata"""
        if not file_path.exists():
            return {}
        
        stat = file_path.stat()
        mime_type, _ = mimetypes.guess_type(str(file_path))
        
        return {
            "size": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "mime_type": mime_type,
            "hash": self._get_file_hash(file_path)
        }
    
    def store_file(self, file_data: Union[bytes, BinaryIO], 
                   file_type: str, filename: str = None,
                   metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Store a file and return storage information
        
        Args:
            file_data: File content as bytes or file-like object
            file_type: Type of file (screenshots, media, evidence)
            filename: Original filename (optional)
            metadata: Additional metadata (optional)
        
        Returns:
            Dictionary with file storage information
        """
        try:
            # Determine file extension
            file_extension = None
            if filename:
                file_extension = Path(filename).suffix
            
            # Generate storage path
            file_path = self._generate_file_path(file_type, file_extension)
            
            # Write file data
            if isinstance(file_data, bytes):
                # Check file size
                if len(file_data) > self.max_file_size:
                    raise ValueError(f"File size exceeds maximum allowed size of {self.max_file_size} bytes")
                
                with open(file_path, "wb") as f:
                    f.write(file_data)
            else:
                # File-like object
                with open(file_path, "wb") as f:
                    shutil.copyfileobj(file_data, f)
                
                # Check file size after writing
                if file_path.stat().st_size > self.max_file_size:
                    file_path.unlink()  # Delete the file
                    raise ValueError(f"File size exceeds maximum allowed size of {self.max_file_size} bytes")
            
            # Get file information
            file_info = self._get_file_info(file_path)
            
            # Build result
            result = {
                "file_id": file_path.stem,
                "file_path": str(file_path.relative_to(self.storage_path)),
                "full_path": str(file_path),
                "url": self._get_file_url(file_path),
                "original_filename": filename,
                "file_type": file_type,
                "metadata": metadata or {},
                **file_info
            }
            
            logger.info(f"Stored file: {file_path} ({file_info['size']} bytes)")
            return result
            
        except Exception as e:
            logger.error(f"Failed to store file: {e}")
            raise
    
    def _get_file_url(self, file_path: Path) -> str:
        """Generate URL for accessing the file"""
        relative_path = file_path.relative_to(self.storage_path)
        return f"/api/files/{relative_path}"
    
    def get_file(self, file_path: str) -> Optional[Path]:
        """Get file by path"""
        try:
            full_path = self.storage_path / file_path
            if full_path.exists() and full_path.is_file():
                return full_path
            return None
        except Exception as e:
            logger.error(f"Failed to get file {file_path}: {e}")
            return None
    
    def delete_file(self, file_path: str) -> bool:
        """Delete a file"""
        try:
            full_path = self.storage_path / file_path
            if full_path.exists() and full_path.is_file():
                full_path.unlink()
                logger.info(f"Deleted file: {full_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete file {file_path}: {e}")
            return False
    
    def store_screenshot(self, screenshot_data: bytes, 
                        source_url: str = None) -> Dict[str, Any]:
        """Store a screenshot with metadata"""
        metadata = {
            "source_url": source_url,
            "capture_time": datetime.utcnow().isoformat(),
            "type": "screenshot"
        }
        
        return self.store_file(
            file_data=screenshot_data,
            file_type="screenshots",
            filename="screenshot.png",
            metadata=metadata
        )
    
    def store_media(self, media_data: bytes, original_url: str = None,
                   filename: str = None) -> Dict[str, Any]:
        """Store media file (image, video, etc.)"""
        metadata = {
            "original_url": original_url,
            "download_time": datetime.utcnow().isoformat(),
            "type": "media"
        }
        
        return self.store_file(
            file_data=media_data,
            file_type="media",
            filename=filename,
            metadata=metadata
        )
    
    def store_evidence(self, evidence_data: bytes, 
                      evidence_type: str = None,
                      filename: str = None) -> Dict[str, Any]:
        """Store evidence file"""
        metadata = {
            "evidence_type": evidence_type,
            "collected_time": datetime.utcnow().isoformat(),
            "type": "evidence"
        }
        
        return self.store_file(
            file_data=evidence_data,
            file_type="evidence",
            filename=filename,
            metadata=metadata
        )
    
    def cleanup_old_files(self, days: int = 30) -> int:
        """Clean up files older than specified days"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            deleted_count = 0
            
            for file_path in self.storage_path.rglob("*"):
                if file_path.is_file():
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_mtime < cutoff_date:
                        try:
                            file_path.unlink()
                            deleted_count += 1
                        except Exception as e:
                            logger.error(f"Failed to delete old file {file_path}: {e}")
            
            logger.info(f"Cleaned up {deleted_count} old files")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup old files: {e}")
            return 0
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics"""
        try:
            stats = {
                "total_files": 0,
                "total_size": 0,
                "by_type": {}
            }
            
            for file_type in ["screenshots", "media", "evidence"]:
                type_dir = self.storage_path / file_type
                if type_dir.exists():
                    type_stats = {"count": 0, "size": 0}
                    
                    for file_path in type_dir.rglob("*"):
                        if file_path.is_file():
                            file_size = file_path.stat().st_size
                            type_stats["count"] += 1
                            type_stats["size"] += file_size
                    
                    stats["by_type"][file_type] = type_stats
                    stats["total_files"] += type_stats["count"]
                    stats["total_size"] += type_stats["size"]
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get storage stats: {e}")
            return {"total_files": 0, "total_size": 0, "by_type": {}}
    
    def health_check(self) -> Dict[str, Any]:
        """Check storage system health"""
        try:
            # Check if storage directory is accessible
            test_file = self.storage_path / "temp" / "health_check.txt"
            test_content = b"health check"
            
            # Write test file
            with open(test_file, "wb") as f:
                f.write(test_content)
            
            # Read test file
            with open(test_file, "rb") as f:
                read_content = f.read()
            
            # Clean up test file
            test_file.unlink()
            
            # Check if content matches
            if read_content == test_content:
                stats = self.get_storage_stats()
                return {
                    "status": "healthy",
                    "storage_path": str(self.storage_path),
                    "writable": True,
                    "readable": True,
                    **stats
                }
            else:
                return {
                    "status": "error",
                    "error": "File content mismatch"
                }
                
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }


# Global file storage service instance
file_storage = FileStorageService()