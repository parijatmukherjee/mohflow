class MohflowError(Exception):
    """Base exception for mohflow"""
    pass

class ConfigurationError(MohflowError):
    """Raised when there's a configuration error"""
    pass