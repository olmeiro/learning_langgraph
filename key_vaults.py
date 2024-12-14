import os
# from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
import logging

logger = logging.getLogger('logger_app.secrets')

class SecretManager:
    """Manages secrets from Azure Key Vault or environment variables."""

    def __init__(self, use_key_vault=True):
        self.use_key_vault = use_key_vault
        self.key_vault_name = os.getenv("KEY_VAULT_NAME", "asiacopilotosusdllo001")
        self.kv_uri = f"https://{self.key_vault_name}.vault.azure.net"
        self.credential = DefaultAzureCredential()

        self.client = (
            SecretClient(vault_url=self.kv_uri, credential=self.credential)
            if use_key_vault
            else None
        )

    def get_secret(self, name):
        """Retrieve secret from Azure Key Vault or environment."""
        if self.use_key_vault:
            try:
                secret = self.client.get_secret(name).value
                return secret
            except Exception as e:
                logger.error(f"Failed to fetch {name} from Key Vault: {e}")

        secret = os.getenv(name)
        if secret:
            pass
        else:
            logger.error(f"Secret {name} not found in environment.")
        return secret

if __name__=="__main__":
    secrets = SecretManager()
    key = secrets.get_secret("smart-openai-endpoint")
    print(key)