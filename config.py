import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL ausente. Configure-a no .env local ou nas variáveis do servidor.")
if not SECRET_KEY or len(SECRET_KEY) < 32:
    raise RuntimeError("SECRET_KEY ausente ou curta. Use uma chave aleatória de pelo menos 32 caracteres.")
