"""
MohFlow Framework Integrations

This package provides first-class integrations with popular Python frameworks:

- FastAPI middleware with automatic request logging
- Django logging integration with middleware
- Flask extension for seamless integration
- Celery task logging with automatic context
- SQLAlchemy query logging integration
- ASGI/WSGI middleware for any framework
- Automatic request/response logging
- Performance monitoring integration

Example usage:

    # FastAPI
    from mohflow.integrations.fastapi import MohFlowMiddleware
    app.add_middleware(MohFlowMiddleware, logger=logger)
    
    # Django
    MIDDLEWARE = [
        'mohflow.integrations.django.MohFlowMiddleware',
        ...
    ]
    
    # Flask  
    from mohflow.integrations.flask import MohFlowExtension
    mohflow = MohFlowExtension(app, logger=logger)
    
    # Celery
    from mohflow.integrations.celery import setup_celery_logging
    setup_celery_logging(logger)
"""

__all__ = []