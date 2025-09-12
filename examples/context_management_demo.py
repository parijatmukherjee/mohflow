#!/usr/bin/env python3
"""
Demo script showing advanced context management features in MohFlow.

This demonstrates:
1. Factory methods (get_logger, create, for_service)
2. Request-scoped context management
3. Thread-local context
4. Temporary context overlays
5. Context chaining patterns
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import asyncio
import threading
import time
from mohflow import MohflowLogger

def demo_factory_methods():
    """Test the new factory methods."""
    print("=== Factory Methods Demo ===")
    
    # Method 1: get_logger (standard pattern)
    logger1 = MohflowLogger.get_logger("demo-service")
    logger1.info("Created with get_logger()")
    
    # Method 2: create (simplified)
    logger2 = MohflowLogger.create("demo-service", log_level="INFO")
    logger2.info("Created with create()")
    
    # Method 3: for_service (clear intent)
    logger3 = MohflowLogger.for_service("demo-service")
    logger3.info("Created with for_service()")
    
    print("✓ All factory methods working\n")

def demo_request_context():
    """Test request-scoped context management."""
    print("=== Request Context Demo ===")
    
    logger = MohflowLogger.smart("context-demo")
    
    # Test request context
    with logger.request_context(request_id="req-123", user_id="user-456"):
        logger.info("Processing user request")
        logger.info("Validating request data", action="validate")
        
        # Nested context maintains parent context
        with logger.request_context(operation="auth", step="login"):
            logger.info("Authenticating user")
            
    # Outside context - no request data
    logger.info("Request completed")
    
    print("✓ Request context management working\n")

def demo_thread_context():
    """Test thread-local context management."""
    print("=== Thread Context Demo ===")
    
    logger = MohflowLogger.smart("thread-demo")
    results = []
    
    def worker_thread(worker_id: int):
        with logger.thread_context(worker_id=f"worker-{worker_id}", thread_name=f"thread-{worker_id}"):
            logger.info(f"Worker {worker_id} starting")
            time.sleep(0.1)
            logger.info(f"Worker {worker_id} processing task", task_id=f"task-{worker_id}")
            results.append(f"Worker {worker_id} completed")
    
    # Start multiple threads
    threads = []
    for i in range(3):
        t = threading.Thread(target=worker_thread, args=(i,))
        threads.append(t)
        t.start()
    
    # Wait for completion
    for t in threads:
        t.join()
    
    logger.info("All workers completed", completed_count=len(results))
    print("✓ Thread context management working\n")

def demo_context_chaining():
    """Test context chaining and temporary overlays."""
    print("=== Context Chaining Demo ===")
    
    logger = MohflowLogger.smart("chaining-demo")
    
    # Set global context
    logger.set_context(service="demo-api", version="1.2.3")
    
    # Use temporary context overlay
    logger.with_context(component="auth", operation="login").info("User login attempt")
    logger.with_context(component="database", query="users").info("Database query executed")
    logger.with_context(component="cache", action="set").info("Cache updated")
    
    # Regular logging still has global context
    logger.info("Global context still active")
    
    print("✓ Context chaining working\n")

def demo_mixed_contexts():
    """Test mixed context scenarios."""
    print("=== Mixed Context Demo ===")
    
    logger = MohflowLogger.smart("mixed-demo")
    
    # Set global context
    logger.set_context(service="api-gateway", environment="production")
    
    # Request context with temporary overlays
    with logger.request_context(request_id="mixed-req-789", endpoint="/api/users"):
        logger.info("Request received")
        
        # Thread context within request
        with logger.thread_context(worker_type="request-handler"):
            logger.info("Processing in background thread")
            
            # Temporary context on top
            logger.with_context(database="users", operation="read").info("Database operation")
            
        logger.info("Request processing completed")
    
    print("✓ Mixed context scenarios working\n")

async def demo_async_context():
    """Test context management with async code."""
    print("=== Async Context Demo ===")
    
    logger = MohflowLogger.smart("async-demo")
    
    async def async_operation(operation_id: str):
        with logger.request_context(operation_id=operation_id, type="async"):
            logger.info(f"Starting async operation {operation_id}")
            await asyncio.sleep(0.1)
            logger.info(f"Async operation {operation_id} completed")
    
    # Run multiple async operations
    tasks = [async_operation(f"op-{i}") for i in range(3)]
    await asyncio.gather(*tasks)
    
    print("✓ Async context management working\n")

def demo_context_info():
    """Test context introspection."""
    print("=== Context Info Demo ===")
    
    logger = MohflowLogger.smart("info-demo")
    
    # Set various contexts
    logger.set_context(service="demo", version="1.0.0")
    
    with logger.request_context(request_id="info-req-123"):
        with logger.thread_context(worker="info-worker"):
            # Get current context
            current_context = logger.get_current_context()
            print(f"Current context keys: {list(current_context.keys())}")
            
            # Get context info
            context_info = logger.context_manager.get_context_info()
            print(f"Active scopes: {len(context_info['active_scopes'])}")
            print(f"Total context keys: {context_info['total_context_keys']}")
            print(f"Request context active: {context_info['request_context_active']}")
            print(f"Thread context active: {context_info['thread_context_active']}")
    
    print("✓ Context introspection working\n")

def main():
    """Run all context management demos."""
    print("🔄 MohFlow Advanced Context Management Demo")
    print("=" * 50)
    
    try:
        # Test factory methods
        demo_factory_methods()
        
        # Test request context
        demo_request_context()
        
        # Test thread context
        demo_thread_context()
        
        # Test context chaining
        demo_context_chaining()
        
        # Test mixed contexts
        demo_mixed_contexts()
        
        # Test async context
        asyncio.run(demo_async_context())
        
        # Test context info
        demo_context_info()
        
        print("🎯 All context management features working correctly!")
        print("✅ Factory methods, request/thread/temporary contexts, chaining all functional")
        
    except Exception as e:
        print(f"❌ Error during demo: {e}")
        import traceback
        traceback.print_exc()
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())