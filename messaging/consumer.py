"""
Message consumer base class for RabbitMQ
"""
import json
import time
import signal
import threading
from typing import Dict, Any, Callable, Optional, List
from abc import ABC, abstractmethod
import pika
from .connection import rabbitmq_connection
from shared.logging_config import logger


class MessageConsumer(ABC):
    """Base class for message consumers"""
    
    def __init__(self, queue_name: str, exchange_name: str = '', 
                 routing_keys: List[str] = None, auto_ack: bool = False,
                 prefetch_count: int = 1):
        self.queue_name = queue_name
        self.exchange_name = exchange_name
        self.routing_keys = routing_keys or ['']
        self.auto_ack = auto_ack
        self.prefetch_count = prefetch_count
        self.is_consuming = False
        self.consumer_tag = None
        self._stop_event = threading.Event()
        self._setup_queue()
    
    def _setup_queue(self):
        """Setup queue and bindings"""
        # Declare queue
        rabbitmq_connection.declare_queue(self.queue_name, durable=True)
        
        # Setup exchange and bindings if specified
        if self.exchange_name:
            rabbitmq_connection.declare_exchange(self.exchange_name)
            
            for routing_key in self.routing_keys:
                rabbitmq_connection.bind_queue(
                    self.queue_name, 
                    self.exchange_name, 
                    routing_key
                )
    
    @abstractmethod
    def process_message(self, message: Dict[str, Any], 
                       delivery_tag: int, properties: pika.BasicProperties) -> bool:
        """
        Process a received message
        
        Args:
            message: Parsed message content
            delivery_tag: Message delivery tag for acknowledgment
            properties: Message properties
        
        Returns:
            bool: True if message processed successfully, False otherwise
        """
        pass
    
    def _message_callback(self, channel, method, properties, body):
        """Internal message callback"""
        try:
            # Parse message
            message = json.loads(body.decode('utf-8'))
            
            logger.debug(f"Received message: {message.get('message_id', 'unknown')}")
            
            # Process message
            success = self.process_message(message, method.delivery_tag, properties)
            
            # Handle acknowledgment
            if not self.auto_ack:
                if success:
                    channel.basic_ack(delivery_tag=method.delivery_tag)
                    logger.debug(f"Message acknowledged: {method.delivery_tag}")
                else:
                    # Reject and requeue the message
                    channel.basic_nack(
                        delivery_tag=method.delivery_tag, 
                        requeue=True
                    )
                    logger.warning(f"Message rejected and requeued: {method.delivery_tag}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message JSON: {e}")
            if not self.auto_ack:
                channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            if not self.auto_ack:
                channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    def start_consuming(self, blocking: bool = True):
        """Start consuming messages"""
        try:
            if self.is_consuming:
                logger.warning("Consumer is already running")
                return
            
            with rabbitmq_connection.get_channel() as channel:
                # Set QoS
                channel.basic_qos(prefetch_count=self.prefetch_count)
                
                # Start consuming
                self.consumer_tag = channel.basic_consume(
                    queue=self.queue_name,
                    on_message_callback=self._message_callback,
                    auto_ack=self.auto_ack
                )
                
                self.is_consuming = True
                logger.info(f"Started consuming from queue: {self.queue_name}")
                
                if blocking:
                    # Setup signal handlers for graceful shutdown
                    signal.signal(signal.SIGINT, self._signal_handler)
                    signal.signal(signal.SIGTERM, self._signal_handler)
                    
                    # Start consuming loop
                    while self.is_consuming and not self._stop_event.is_set():
                        try:
                            channel.connection.process_data_events(time_limit=1)
                        except KeyboardInterrupt:
                            logger.info("Received interrupt signal, stopping consumer...")
                            break
                        except Exception as e:
                            logger.error(f"Error in consuming loop: {e}")
                            time.sleep(1)
                    
                    self.stop_consuming()
                
        except Exception as e:
            logger.error(f"Failed to start consuming: {e}")
            self.is_consuming = False
    
    def stop_consuming(self):
        """Stop consuming messages"""
        try:
            if not self.is_consuming:
                return
            
            self.is_consuming = False
            self._stop_event.set()
            
            if self.consumer_tag:
                with rabbitmq_connection.get_channel() as channel:
                    channel.basic_cancel(self.consumer_tag)
                    logger.info(f"Stopped consuming from queue: {self.queue_name}")
            
        except Exception as e:
            logger.error(f"Error stopping consumer: {e}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.stop_consuming()


class WorkerConsumer(MessageConsumer):
    """Consumer for processing worker tasks"""
    
    def __init__(self, worker_type: str, process_func: Callable):
        self.worker_type = worker_type
        self.process_func = process_func
        
        queue_name = f"worker_{worker_type}"
        super().__init__(
            queue_name=queue_name,
            exchange_name='threat_data',
            routing_keys=[f"*.{worker_type}", f"{worker_type}.*"],
            prefetch_count=5
        )
    
    def process_message(self, message: Dict[str, Any], 
                       delivery_tag: int, properties: pika.BasicProperties) -> bool:
        """Process worker task message"""
        try:
            logger.info(f"Processing {self.worker_type} task: {message.get('message_id')}")
            
            # Call the processing function
            result = self.process_func(message)
            
            if result:
                logger.info(f"Successfully processed {self.worker_type} task")
                return True
            else:
                logger.error(f"Failed to process {self.worker_type} task")
                return False
                
        except Exception as e:
            logger.error(f"Error in {self.worker_type} worker: {e}")
            return False


class AnalysisConsumer(MessageConsumer):
    """Consumer for analysis tasks"""
    
    def __init__(self, analysis_modules: Dict[str, Callable]):
        self.analysis_modules = analysis_modules
        
        super().__init__(
            queue_name="analysis_queue",
            exchange_name='threat_data',
            routing_keys=['social.*', 'scraping.*', 'messaging.*'],
            prefetch_count=3
        )
    
    def process_message(self, message: Dict[str, Any], 
                       delivery_tag: int, properties: pika.BasicProperties) -> bool:
        """Process analysis task"""
        try:
            message_type = message.get('type')
            data = message.get('data', {})
            
            logger.info(f"Analyzing {message_type} data: {message.get('message_id')}")
            
            # Run applicable analysis modules
            analysis_results = {}
            for module_name, module_func in self.analysis_modules.items():
                try:
                    result = module_func(data, message_type)
                    if result:
                        analysis_results[module_name] = result
                except Exception as e:
                    logger.error(f"Analysis module {module_name} failed: {e}")
            
            # Publish analysis results if any
            if analysis_results:
                from .producer import analysis_producer
                analysis_producer.publish_threat_analysis(
                    analysis_result=analysis_results,
                    analysis_type=message_type
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Error in analysis consumer: {e}")
            return False


class EvidenceConsumer(MessageConsumer):
    """Consumer for evidence collection tasks"""
    
    def __init__(self, evidence_handlers: Dict[str, Callable]):
        self.evidence_handlers = evidence_handlers
        
        super().__init__(
            queue_name="evidence_queue",
            exchange_name='evidence',
            routing_keys=['screenshot', 'media_download'],
            prefetch_count=2
        )
    
    def process_message(self, message: Dict[str, Any], 
                       delivery_tag: int, properties: pika.BasicProperties) -> bool:
        """Process evidence collection task"""
        try:
            task_type = message.get('type')
            
            if task_type in self.evidence_handlers:
                handler = self.evidence_handlers[task_type]
                result = handler(message)
                
                if result:
                    logger.info(f"Evidence collection completed: {task_type}")
                    return True
                else:
                    logger.error(f"Evidence collection failed: {task_type}")
                    return False
            else:
                logger.warning(f"No handler for evidence task type: {task_type}")
                return False
                
        except Exception as e:
            logger.error(f"Error in evidence consumer: {e}")
            return False


class AlertConsumer(MessageConsumer):
    """Consumer for alert processing"""
    
    def __init__(self, alert_handlers: Dict[str, Callable]):
        self.alert_handlers = alert_handlers
        
        super().__init__(
            queue_name="alert_queue",
            exchange_name='analysis',
            routing_keys=['incident.*', 'threat.*'],
            prefetch_count=10  # Higher throughput for alerts
        )
    
    def process_message(self, message: Dict[str, Any], 
                       delivery_tag: int, properties: pika.BasicProperties) -> bool:
        """Process alert message"""
        try:
            message_type = message.get('type')
            severity = message.get('severity', 'medium')
            
            logger.info(f"Processing alert: {message_type} (severity: {severity})")
            
            # Route to appropriate handler
            if message_type in self.alert_handlers:
                handler = self.alert_handlers[message_type]
                result = handler(message)
                
                if result:
                    logger.info(f"Alert processed successfully: {message_type}")
                    return True
                else:
                    logger.error(f"Alert processing failed: {message_type}")
                    return False
            else:
                logger.warning(f"No handler for alert type: {message_type}")
                return False
                
        except Exception as e:
            logger.error(f"Error in alert consumer: {e}")
            return False