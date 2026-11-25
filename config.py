"""
CONFIGURAÇÕES DO SISTEMA - edite só este arquivo.
Quando o app.py for atualizado, estas configurações continuam as mesmas.
"""

import os

# Conexão com o MySQL
DB_CONFIG = dict(
    host=os.environ.get("DB_HOST", "mysql-13eb576-freiredecarvalhoandrelucas-2466.j.aivencloud.com"),
    port=int(os.environ.get("DB_PORT", 22597)),
    user=os.environ.get("DB_USER", "avnadmin"),
    password=os.environ.get("DB_PASSWORD", ""),
    database=os.environ.get("DB_NAME", "defaultdb"),
    charset="utf8mb4",
    collation="utf8mb4_unicode_ci",
    ssl={"ssl": {}},
)
# Login do relatório
LOGIN_USUARIO = "ADM"   # não diferencia maiúsculas de minúsculas
LOGIN_SENHA = "ADM"     # diferencia maiúsculas de minúsculas

