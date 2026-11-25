"""
TROMBETAS E FESTAS - Servidor (Flask + MySQL)

Como rodar:
  1) pip install -r requirements.txt
  2) Confira a senha do MySQL no arquivo config.py
  3) python app.py
  4) Abra http://localhost:5000
"""
import io
import hmac
import secrets
import datetime
from functools import wraps
import mysql.connector
from flask import Flask, request, jsonify, send_file, send_from_directory, session
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from config import DB_CONFIG, LOGIN_USUARIO, LOGIN_SENHA

ORIGENS_VALIDAS = {
    "Instagram",
    "Evangelização na feira",
    "Outdoor no portão da igreja",
    "Convidado por membro",
    "Outro",
}
GRUPOS_VALIDOS = {1, 2, 3, 4}

app = Flask(__name__, static_folder="static")
# Chave que protege o login. É gerada a cada vez que o servidor liga,
# então, ao reiniciar o servidor, todos precisam entrar de novo.
app.secret_key = secrets.token_hex(32)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def conectar():
    return mysql.connector.connect(**DB_CONFIG)


def limpar_texto(valor):
    """Remove espaços sobrando: '  Marcelo   Silva ' -> 'Marcelo Silva'."""
    return " ".join(str(valor or "").split())


def escapar_like(texto):
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def achar_membro(cur, digitado):
    """
    Procura o membro pelo nome digitado (ignora maiúsculas e acentos).
    Tenta, nesta ordem, e para na primeira que achar UM único membro:
      1) nome exatamente igual;
      2) nome que começa com as palavras digitadas (ex.: 'Matheus' -> 'Matheus Vicente ...',
         mas 'Andre' NÃO pega 'Andrea');
      3) nome que começa com o texto digitado (ex.: 'Marc' -> 'Marcelo ...').
    Se uma etapa achar mais de um membro, não adivinha e devolve None.
    Devolve (id, grupo_id) ou None.
    """
    texto = escapar_like(digitado)
    etapas = (
        ("SELECT id, grupo_id FROM membros WHERE nome = %s", digitado),
        ("SELECT id, grupo_id FROM membros WHERE nome LIKE %s", texto + " %"),
        ("SELECT id, grupo_id FROM membros WHERE nome LIKE %s", texto + "%"),
    )
    for sql, valor in etapas:
        cur.execute(sql, (valor,))
        achados = cur.fetchall()
        if len(achados) == 1:
            return achados[0]
        if len(achados) > 1:
            return None
    return None


# ---------------------------------------------------------------------
# PÁGINA
# ---------------------------------------------------------------------
@app.get("/")
def index():
    return send_from_directory("static", "index.html")


# ---------------------------------------------------------------------
# CADASTRO DE VISITANTE
# ---------------------------------------------------------------------
@app.post("/api/visitantes")
def criar_visitante():
    dados = request.get_json(silent=True) or {}
    nome = limpar_texto(dados.get("nome"))
    origem = limpar_texto(dados.get("origem"))
    origem_outro = limpar_texto(dados.get("origem_outro"))
    convidado_por = limpar_texto(dados.get("convidado_por"))

    if not nome:
        return jsonify(erro="Informe o nome do visitante."), 400
    if origem not in ORIGENS_VALIDAS:
        return jsonify(erro="Origem inválida."), 400
    if origem == "Outro" and not origem_outro:
        return jsonify(erro="Escreva como a pessoa soube do evento."), 400
    if origem != "Outro":
        origem_outro = ""

    conn = conectar()
    try:
        cur = conn.cursor()
        membro = achar_membro(cur, convidado_por) if convidado_por else None
        membro_id, grupo_id = (membro if membro else (None, None))

        # "a conferir": digitou um nome que não achou 1 membro único,
        # ou marcou "Convidado por membro" sem digitar o nome.
        a_conferir = 1 if (
            (convidado_por and not membro)
            or (origem == "Convidado por membro" and not convidado_por)
        ) else 0

        cur.execute(
            """INSERT INTO visitantes
               (nome, origem, origem_outro, convidado_por, membro_id, grupo_id, grupo_a_conferir)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (nome, origem, origem_outro or None, convidado_por or None, membro_id, grupo_id, a_conferir),
        )
        conn.commit()

        nome_grupo = None
        if grupo_id:
            cur.execute("SELECT nome FROM grupos WHERE id = %s", (grupo_id,))
            nome_grupo = cur.fetchone()[0]
        return jsonify(ok=True, grupo=nome_grupo, a_conferir=bool(a_conferir))
    finally:
        conn.close()


# ---------------------------------------------------------------------
# CONTROLE DE MEMBROS (quantidade por grupo)
# ---------------------------------------------------------------------
@app.post("/api/membros")
def registrar_membros():
    dados = request.get_json(silent=True) or {}
    qtd = dados.get("quantidade")
    if isinstance(qtd, bool) or not isinstance(qtd, int) or qtd < 0:
        return jsonify(erro="Quantidade inválida."), 400

    conn = conectar()
    try:
        cur = conn.cursor()
        # Quantidade total de membros presentes (sem grupo): grupo_id fica vazio.
        cur.execute(
            "INSERT INTO contagem_membros (grupo_id, quantidade) VALUES (NULL, %s)", (qtd,)
        )
        conn.commit()
        return jsonify(ok=True)
    finally:
        conn.close()


# ---------------------------------------------------------------------
# SUGESTÕES DE MEMBROS (aparecem enquanto a pessoa digita o nome)
# ---------------------------------------------------------------------
@app.get("/api/membros/busca")
def buscar_membros():
    q = limpar_texto(request.args.get("q"))
    if len(q) < 2:
        return jsonify(membros=[])
    texto = escapar_like(q)
    conn = conectar()
    try:
        cur = conn.cursor()
        # nomes que começam com o texto OU que têm alguma palavra começando com ele
        cur.execute(
            """SELECT m.nome, g.nome
               FROM membros m JOIN grupos g ON g.id = m.grupo_id
               WHERE m.nome LIKE %s OR m.nome LIKE %s
               ORDER BY (m.nome LIKE %s) DESC, m.nome LIMIT 8""",
            (texto + "%", "% " + texto + "%", texto + "%"),
        )
        return jsonify(membros=[{"nome": n, "grupo": g} for n, g in cur.fetchall()])
    finally:
        conn.close()


# ---------------------------------------------------------------------
# LOGIN (só o relatório é protegido)
# ---------------------------------------------------------------------
def exige_login(funcao):
    @wraps(funcao)
    def interna(*args, **kwargs):
        if not session.get("logado"):
            return jsonify(erro="Faça login para continuar."), 401
        return funcao(*args, **kwargs)
    return interna


@app.get("/api/sessao")
def sessao():
    return jsonify(logado=bool(session.get("logado")))


@app.post("/api/login")
def login():
    dados = request.get_json(silent=True) or {}
    usuario = str(dados.get("usuario", "")).strip()
    senha = str(dados.get("senha", ""))
    usuario_ok = hmac.compare_digest(usuario.upper().encode(), LOGIN_USUARIO.upper().encode())
    senha_ok = hmac.compare_digest(senha.encode(), LOGIN_SENHA.encode())
    if usuario_ok and senha_ok:
        session["logado"] = True
        return jsonify(ok=True)
    return jsonify(erro="Usuário ou senha incorretos."), 401


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


# ---------------------------------------------------------------------
# RELATÓRIO EXCEL
# ---------------------------------------------------------------------
def estilizar_cabecalho(ws, linha, colunas):
    for c in range(1, colunas + 1):
        cel = ws.cell(row=linha, column=c)
        cel.font = Font(bold=True, color="FFFFFF")
        cel.fill = PatternFill("solid", fgColor="14284B")
        cel.alignment = Alignment(vertical="center")


def ajustar_larguras(ws):
    for col in ws.columns:
        maior = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(maior + 3, 45)


@app.get("/api/relatorio.xlsx")
@exige_login
def relatorio_excel():
    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT g.nome, COUNT(v.id)
               FROM grupos g LEFT JOIN visitantes v ON v.grupo_id = g.id
               GROUP BY g.id, g.nome ORDER BY g.id"""
        )
        resumo = cur.fetchall()
        cur.execute(
            """SELECT quantidade FROM contagem_membros
               WHERE grupo_id IS NULL ORDER BY registrado_em DESC, id DESC LIMIT 1"""
        )
        linha = cur.fetchone()
        total_membros = linha[0] if linha else 0
        cur.execute("SELECT COUNT(*) FROM visitantes WHERE grupo_id IS NULL")
        sem_grupo = cur.fetchone()[0]
        cur.execute("SELECT origem, COUNT(*) FROM visitantes GROUP BY origem ORDER BY origem")
        por_origem = cur.fetchall()
        cur.execute(
            """SELECT visitante, origem, origem_outro, membro_digitado, membro_encontrado,
                      grupo, a_conferir, criado_em
               FROM vw_relatorio_visitantes"""
        )
        visitantes = cur.fetchall()
    finally:
        conn.close()

    total_visitantes = len(visitantes)

    wb = Workbook()

    # --- Aba Resumo ---
    ws = wb.active
    ws.title = "Resumo"
    ws.append(["Grupo", "Visitantes trazidos"])
    estilizar_cabecalho(ws, 1, 2)
    for grupo, trazidos in resumo:
        ws.append([grupo, trazidos])
    ws.append(["Sem grupo", sem_grupo])
    ws.append(["TOTAL DE VISITANTES", total_visitantes])
    for c in range(1, 3):
        ws.cell(row=ws.max_row, column=c).font = Font(bold=True)
    ws.append([])
    ws.append(["Membros presentes", total_membros])
    ws.append(["Público total (membros + visitantes)", total_membros + total_visitantes])
    for linha_resumo in (ws.max_row - 1, ws.max_row):
        ws.cell(row=linha_resumo, column=1).font = Font(bold=True)
    ws.append([])
    ws.append(["Origem do visitante", "Quantidade"])
    estilizar_cabecalho(ws, ws.max_row, 2)
    for origem, qtd in por_origem:
        ws.append([origem, qtd])
    ajustar_larguras(ws)

    # --- Aba Visitantes ---
    wv = wb.create_sheet("Visitantes")
    wv.append(["Visitante", "Origem", "Detalhe do \"Outro\"", "Membro digitado", "Membro encontrado",
               "Grupo", "A conferir", "Data/Hora"])
    estilizar_cabecalho(wv, 1, 8)
    for linha in visitantes:
        wv.append([x if x is not None else "" for x in linha])
        wv.cell(row=wv.max_row, column=8).number_format = "dd/mm/yyyy hh:mm"
    wv.freeze_panes = "A2"
    ajustar_larguras(wv)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    nome_arquivo = f"relatorio_trombetas_{datetime.datetime.now():%Y%m%d_%H%M}.xlsx"
    return send_file(
        buf, as_attachment=True, download_name=nome_arquivo,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.errorhandler(mysql.connector.Error)
def erro_banco(e):
    app.logger.error("Erro no MySQL: %s", e)
    return jsonify(erro="Não foi possível acessar o banco de dados."), 500


if __name__ == "__main__":
    # host 0.0.0.0 permite acessar pelo celular, na mesma rede: http://IP-DO-COMPUTADOR:5000
    app.run(host="0.0.0.0", port=5000, debug=False)