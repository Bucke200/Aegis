"""
RabbitMQ connection management
"""
import pika
import json
import time
from typing import Optional, Dict, Any
from contextlib import contextmanager
from shared.config import settings
from shared.logging_config import logger


class RabbitMQConnection:
    """Manages RabbitMQ connections with automatic reconnection"""
    
    def __init__(self):
        self.connection: Optional[pika.BlockingConnection] = None
        self.channel: Optional[pika.channel.Channel] = None
        self._connection_params = None
        self._setup_connection_params()
        # Don't auto-connect on init
    
    def _setup_connection_params(self):
        """Setup connection parameters from config"""
        self._connection_params = pika.ConnectionParameters(
            host=settings.rabbitmq_host,
            port=settings.rabbitmq_port,
            virtual_host=settings.rabbitmq_vhost,
            credentials=pika.PlainCredentials(
                settings.rabbitmq_user,
                settings.rabbitmq_password
            ),
            heartbeat=600,
            blocked_connection_timeout=300,
        )
    
    def connect(self) -> bool:
        """Establish connection to RabbitMQ"""
        try:
            if self.is_connected():
                return True
            
            logger.info("Connecting to RabbitMQ...")
            self.connection = pika.BlockingConnection(self._connection_params)
            self.channel = self.connection.channel()
            
            # Enable delivery confirmations
            self.channel.confirm_delivery()
            
            logger.info("Successfully connected to RabbitMQ")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            self.connection = None
            self.channel = None
            return False
    
    def disconnect(self):
        """Close RabbitMQ connection"""
        try:
            if self.channel and not self.channel.is_closed:
                self.channel.close()
            if self.connection and not self.connection.is_closed:
                self.connection.close()
        except Exception as e:
            logger.error(f"Error disconnecting from RabbitMQ: {e}")
        finally:
            self.channel = None
            self.connection = None
    
    def is_connected(self) -> bool:
        """Check if connection is active"""
        return (
            self.connection is not None 
            and not self.connection.is_closed 
            and self.channel is not None 
            and not self.channel.is_closed
        )
    
    def reconnect(self, max_retries: int = 5, delay: float = 1.0) -> bool:
        """Reconnect with exponential backoff"""
        for attempt in range(max_retries):
            if self.connect():
                return True
            
            if attempt < max_retries - 1:
                wait_time = delay * (2 ** attempt)
                logger.warning(f"Reconnection attempt {attempt + 1} failed, retrying in {wait_time}s...")
                time.sleep(wait_time)
        
        logger.error(f"Failed to reconnect after {max_retries} attempts")
        return False
    
    @contextmanager
    def get_channel(self):
        """Context manager for getting a channel with automatic reconnection"""
        if not self.is_connected():
            if not self.reconnect():
                raise ConnectionError("Could not establish RabbitMQ connection")
        
        try:
            yield self.channel
        except (pika.exceptions.ConnectionClosed, pika.exceptions.ChannelClosed) as e:
            logger.warning(f"Connection lost: {e}, attempting to reconnect...")
            if self.reconnect():
                yield self.channel
            else:
                raise ConnectionError("Could not reconnect to RabbitMQ")
    
    def declare_queue(self, queue_name: str, durable: bool = True, **kwargs) -> bool:
        """Declare a queue"""
        try:
            with self.get_channel() as channel:
                channel.queue_declare(queue=queue_name, durable=durable, **kwargs)
                logger.info(f"Queue '{queue_name}' declared successfully")
                return True
        except Exception as e:
            logger.error(f"Failed to declare queue '{queue_name}': {e}")
            return False
    
    def declare_exchange(self, exchange_name: str, exchange_type: str = 'direct', 
                        durable: bool = True, **kwargs) -> bool:
        """Declare an exchange"""
        try:
            with self.get_channel() as channel:
                channel.exchange_declare(
                    exchange=exchange_name, 
                    exchange_type=exchange_type,
                    durable=durable,
                    **kwargs
                )
                logger.info(f"Exchange '{exchange_name}' declared successfully")
                return True
        except Exception as e:
            logger.error(f"Failed to declare exchange '{exchange_name}': {e}")
            return False
    
    def bind_queue(self, queue_name: str, exchange_name: str, routing_key: str = '') -> bool:
        """Bind queue to exchange"""
        try:
            with self.get_channel() as channel:
                channel.queue_bind(
                    exchange=exchange_name,
                    queue=queue_name,
                    routing_key=routing_key
                )
                logger.info(f"Queue '{queue_name}' bound to exchange '{exchange_name}' with routing key '{routing_key}'")
                return True
        except Exception as e:
            logger.error(f"Failed to bind queue '{queue_name}' to exchange '{exchange_name}': {e}")
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """Check RabbitMQ connection health"""
        try:
            if not self.is_connected():
                if not self.connect():
                    return {
                        "status": "unhealthy",
                        "error": "Cannot connect to RabbitMQ"
                    }
            
            # Test basic operations
            test_queue = "health_check_queue"
            with self.get_channel() as channel:
                # Declare a temporary queue
                channel.queue_declare(queue=test_queue, durable=False, auto_delete=True)
                
                # Send a test message
                test_message = {"test": "health_check", "timestamp": time.time()}
                channel.basic_publish(
                    exchange='',
                    routing_key=test_queue,
                    body=json.dumps(test_message),
                    properties=pika.BasicProperties(delivery_mode=1)  # Non-persistent
                )
                
                # Clean up
                channel.queue_delete(queue=test_queue)
            
            return {
                "status": "healthy",
                "connection": "active",
                "host": settings.rabbitmq_host,
                "port": settings.rabbitmq_port
            }
            
        except Exception as e:
            logger.error(f"RabbitMQ health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# Global connection instance
rabbitmq_connection = RabbitMQConnection()