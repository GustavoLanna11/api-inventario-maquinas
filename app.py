from flask import Flask, request, jsonify, Response
import os
import json
from base64 import b64decode
from database import get_collection
from pymongo.errors import DuplicateKeyError

app = Flask(__name__)

# Token vindo do ambiente (Render)
SECRET_TOKEN = os.environ.get("API_SECRET_TOKEN")

collection = get_collection()

try:
    collection.create_index("Nome da máquina", unique=True)
    print("🔒 Índice único criado para 'Nome da máquina'")
except Exception as e:
    print(f"⚠️ Índice já existe ou erro ao criar: {e}")


# Rota de Health para monitoramento do serviço
@app.route("/health", methods=["GET"])
def health():
    try:
        total = collection.count_documents({})
        return jsonify({
            "status": "ok",
            "service": "api-inventario",
            "mongo": "connected",
        }), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "service": "api-inventario",
            "mongo": "disconnected",
            "error": str(e)
        }), 500


# Login (Basic Auth)
def validar_login():
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Basic "):
        return False, Response(
            "Login necessário",
            401,
            {"WWW-Authenticate": 'Basic realm="Login Required"'}
        )

    try:
        encoded = auth_header.split(" ")[1]
        decoded = b64decode(encoded).decode("utf-8")
        username, password = decoded.split(":")

        if (
            username == os.environ.get("API_USER") and
            password == os.environ.get("API_PASSWORD")
        ):
            return True, None
    except:
        pass

    return False, Response(
        "Credenciais inválidas",
        401,
        {"WWW-Authenticate": 'Basic realm="Login Required"'}
    )


# POST protegido por TOKEN
@app.route("/upload_excel", methods=["POST"])
def upload_excel():
    token = request.headers.get("Authorization")

    if not SECRET_TOKEN:
        return jsonify({"error": "Token não configurado na API"}), 500

    if token != f"Bearer {SECRET_TOKEN}":
        return jsonify({"error": "Não autorizado"}), 401

    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "JSON não enviado"}), 400

        if isinstance(data, dict):
            data = [data]

        for doc in data:
            nome_maquina = doc.get("Nome da máquina")

            if not nome_maquina:
                return jsonify({"error": "Nome da máquina é obrigatório"}), 400

            print("➡️ Processando:", nome_maquina, doc.get("Número de Série"))

            filtro = {"Nome da máquina": nome_maquina}

            try:
                collection.update_one(filtro, {"$set": doc}, upsert=True)
            except DuplicateKeyError:
                return jsonify({
                    "error": "Máquina duplicada (nome já existe)"
                }), 409

        print("📦 Dados recebidos:", data)

        return jsonify({"message": "✅ Dados inseridos/atualizados no MongoDB!"})

    except Exception as e:
        print(f"❌ Erro upload: {e}")
        return jsonify({"error": str(e)}), 500


# GET protegido por LOGIN
@app.route("/dados", methods=["GET"])
def listar_dados():
    autorizado, erro = validar_login()
    if not autorizado:
        return erro

    try:
        dados = list(collection.find({}, {"_id": 0}))
        json_str = json.dumps(dados, ensure_ascii=False)
        return Response(json_str, mimetype="application/json")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# GET protegido por LOGIN
@app.route("/mongo_info", methods=["GET"])
def mongo_info():
    autorizado, erro = validar_login()
    if not autorizado:
        return erro

    try:
        total = collection.count_documents({})
        return jsonify({
            "status": "MongoDB conectado",
            "documentos": total
        })
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("🚀 API rodando com MongoDB (modo JSON)")
    app.run(host="0.0.0.0", port=port)