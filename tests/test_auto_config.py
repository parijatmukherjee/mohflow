"""Tests for auto-configuration module."""

import pytest
from unittest.mock import Mock, patch, mock_open
from mohflow.auto_config import AutoConfigurator, EnvironmentInfo


class TestAutoConfigurator:
    """Test cases for AutoConfigurator class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.configurator = AutoConfigurator()

    @patch('os.environ.get')
    def test_detect_aws_environment(self, mock_env_get):
        """Test AWS environment detection."""
        # Mock AWS environment variables
        def env_side_effect(key, default=None):
            aws_vars = {
                'AWS_REGION': 'us-east-1',
                'AWS_EXECUTION_ENV': 'AWS_Lambda_python3.9',
                'AWS_LAMBDA_FUNCTION_NAME': 'test-function'
            }
            return aws_vars.get(key, default)
        
        mock_env_get.side_effect = env_side_effect
        
        env_info = self.configurator.detect_environment()
        
        assert env_info.cloud_provider == 'aws'
        assert env_info.region == 'us-east-1'
        assert 'AWS_Lambda' in env_info.runtime

    @patch('os.environ.get')
    def test_detect_gcp_environment(self, mock_env_get):
        """Test GCP environment detection."""
        def env_side_effect(key, default=None):
            gcp_vars = {
                'GOOGLE_CLOUD_PROJECT': 'test-project',
                'GCLOUD_PROJECT': 'test-project',
                'K_SERVICE': 'test-service'
            }
            return gcp_vars.get(key, default)
        
        mock_env_get.side_effect = env_side_effect
        
        env_info = self.configurator.detect_environment()
        
        assert env_info.cloud_provider == 'gcp'
        assert env_info.project_id == 'test-project'

    @patch('os.environ.get')
    def test_detect_azure_environment(self, mock_env_get):
        """Test Azure environment detection."""
        def env_side_effect(key, default=None):
            azure_vars = {
                'AZURE_CLIENT_ID': 'test-client-id',
                'WEBSITE_SITE_NAME': 'test-app'
            }
            return azure_vars.get(key, default)
        
        mock_env_get.side_effect = env_side_effect
        
        env_info = self.configurator.detect_environment()
        
        assert env_info.cloud_provider == 'azure'

    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='test-namespace')
    def test_detect_kubernetes_environment(self, mock_file, mock_exists):
        """Test Kubernetes environment detection."""
        mock_exists.return_value = True
        
        env_info = self.configurator.detect_environment()
        
        assert env_info.orchestrator == 'kubernetes'
        assert env_info.namespace == 'test-namespace'

    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='{"Config": {"Hostname": "container123"}}')
    def test_detect_docker_environment(self, mock_file, mock_exists):
        """Test Docker environment detection."""
        mock_exists.return_value = True
        
        env_info = self.configurator.detect_environment()
        
        assert env_info.container_runtime == 'docker'

    def test_detect_local_environment(self):
        """Test local environment detection."""
        with patch('os.environ.get', return_value=None), \
             patch('os.path.exists', return_value=False):
            
            env_info = self.configurator.detect_environment()
            
            assert env_info.cloud_provider == 'local'
            assert env_info.environment_type == 'development'

    def test_get_auto_config_basic(self):
        """Test basic auto-configuration generation."""
        env_info = EnvironmentInfo(
            cloud_provider='aws',
            region='us-east-1',
            environment_type='production'
        )
        
        config = self.configurator.get_auto_config(env_info, 'test-service')
        
        assert config['service_name'] == 'test-service'
        assert config['environment'] == 'production'
        assert config['region'] == 'us-east-1'
        assert config['cloud_provider'] == 'aws'

    def test_get_auto_config_kubernetes(self):
        """Test auto-configuration for Kubernetes."""
        env_info = EnvironmentInfo(
            cloud_provider='gcp',
            orchestrator='kubernetes',
            namespace='prod-namespace',
            environment_type='production'
        )
        
        config = self.configurator.get_auto_config(env_info, 'k8s-service')
        
        assert config['orchestrator'] == 'kubernetes'
        assert config['namespace'] == 'prod-namespace'
        assert 'context_enrichment' in config
        assert config['context_enrichment']['include_system_info'] is True

    def test_get_auto_config_lambda(self):
        """Test auto-configuration for AWS Lambda."""
        env_info = EnvironmentInfo(
            cloud_provider='aws',
            runtime='AWS_Lambda_python3.9',
            region='us-west-2',
            environment_type='production'
        )
        
        config = self.configurator.get_auto_config(env_info, 'lambda-function')
        
        assert config['runtime'] == 'AWS_Lambda_python3.9'
        assert config['region'] == 'us-west-2'

    def test_apply_auto_configuration(self):
        """Test applying auto-configuration to existing config."""
        existing_config = {
            'service_name': 'test-service',
            'log_level': 'DEBUG'
        }
        
        with patch.object(self.configurator, 'detect_environment') as mock_detect:
            mock_detect.return_value = EnvironmentInfo(
                cloud_provider='aws',
                region='us-east-1',
                environment_type='production'
            )
            
            result = self.configurator.apply_auto_configuration(existing_config)
            
            # Should preserve existing config
            assert result['service_name'] == 'test-service'
            assert result['log_level'] == 'DEBUG'
            
            # Should add auto-detected values
            assert result['cloud_provider'] == 'aws'
            assert result['region'] == 'us-east-1'
            assert result['environment'] == 'production'

    @patch('socket.gethostname')
    def test_get_system_info(self, mock_hostname):
        """Test system information gathering."""
        mock_hostname.return_value = 'test-host'
        
        sys_info = self.configurator._get_system_info()
        
        assert sys_info['hostname'] == 'test-host'
        assert 'process_id' in sys_info
        assert 'python_version' in sys_info

    def test_environment_info_creation(self):
        """Test EnvironmentInfo dataclass creation."""
        env_info = EnvironmentInfo(
            cloud_provider='aws',
            region='us-east-1',
            environment_type='production',
            orchestrator='kubernetes',
            namespace='default',
            runtime='python3.9'
        )
        
        assert env_info.cloud_provider == 'aws'
        assert env_info.region == 'us-east-1'
        assert env_info.environment_type == 'production'
        assert env_info.orchestrator == 'kubernetes'
        assert env_info.namespace == 'default'
        assert env_info.runtime == 'python3.9'

    def test_environment_info_defaults(self):
        """Test EnvironmentInfo default values."""
        env_info = EnvironmentInfo(cloud_provider='local')
        
        assert env_info.cloud_provider == 'local'
        assert env_info.region is None
        assert env_info.environment_type == 'development'
        assert env_info.orchestrator is None