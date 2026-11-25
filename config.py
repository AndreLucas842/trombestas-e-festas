"""
CONFIGURAÇÕES DO SISTEMA - edite só este arquivo.
Quando o app.py for atualizado, estas configurações continuam as mesmas.
"""

# Conexão com o MySQL
DB_CONFIG = dict(
    host="localhost",
    port=3306,
    user="root",
    password="",          # <<< troque se a senha do seu MySQL for outra
    database="trombetas_festas",
    charset="utf8mb4",
    collation="utf8mb4_unicode_ci",
)

# Login do relatório
LOGIN_USUARIO = "ADM"   # não diferencia maiúsculas de minúsculas
LOGIN_SENHA = "ADM"     # diferencia maiúsculas de minúsculas