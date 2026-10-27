from flask import Flask, request, jsonify
from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError
from datetime import datetime, timezone
from bson import ObjectId
from functools import wraps
import os
import logging
import math

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI")
API_SECRET_TOKEN = os.getenv("API_SECRET_TOKEN")
API_USER = os.getenv("API_USER")
API_PASSWORD = os.getenv("API_PASSWORD")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI não configurada")

client = MongoClient(MONGO_URI)
db = client.get_default_database()

collection = db["maquinas"]

collection.create_index(
    [("Nome da máquina", ASCENDING)],
    unique=True
)


def get_collection():
    return db["maquinas"]


def get_tentativas_collection():
    return db["tentativas_cadastro"]


def basic_auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization

        if not auth:
            return jsonify({"erro": "Autenticação necessária"}), 401

        if auth.username != API_USER or auth.password != API_PASSWORD:
            return jsonify({"erro": "Usuário ou senha inválidos"}), 401

        return f(*args, **kwargs)

    return decorated


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return jsonify({"erro": "Token não informado"}), 401

        token = auth_header.replace("Bearer ", "", 1)

        if token != API_SECRET_TOKEN:
            return jsonify({"erro": "Token inválido"}), 403

        return f(*args, **kwargs)

    return decorated


def serialize_document(doc):
    if not doc:
        return None

    doc["_id"] = str(doc["_id"])

    for key, value in list(doc.items()):
        if isinstance(value, datetime):
            doc[key] = value.isoformat()

    return doc


def serial_valido(serial):
    if not serial:
        return False

    serial = str(serial).strip()

    if not serial:
        return False

    invalidos = {
        "filled by oem",
        "to be filled by o.e.m.",
        "default string",
        "unknown",
        "n/a",
        "na",
        "none",
        "null",
        "serial number",
    }

    return serial.lower() not in invalidos


def serial_normalizado(serial):
    return str(serial).strip().lower()


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "online"
    })


@app.route("/upload_excel", methods=["POST"])
@token_required
def upload_excel():
    dados = request.get_json(silent=True)

    if not dados:
        return jsonify({
            "erro": "JSON não informado"
        }), 400

    if isinstance(dados, dict):
        maquinas = dados.get("maquinas", [])

        if not maquinas:
            maquinas = [dados]
    elif isinstance(dados, list):
        maquinas = dados
    else:
        return jsonify({
            "erro": "Formato inválido"
        }), 400

    col = get_collection()
    tentativas = get_tentativas_collection()

    inseridas = 0
    atualizadas = 0
    pendentes = 0
    erros = []

    campos_admin = [
        "Etiqueta",
        "Cidade",
        "Departamento",
        "Unidade Residente",
        "Observações"
    ]

    for maquina in maquinas:
        try:
            nome = str(
                maquina.get("Nome da máquina", "")
            ).strip()

            if not nome:
                continue

            existente = col.find_one({
                "Nome da máquina": nome
            })

            if existente:
                update_data = {}

                for campo in campos_admin:
                    if campo in existente:
                        update_data[campo] = existente[campo]

                for campo, valor in maquina.items():
                    if campo not in campos_admin:
                        update_data[campo] = valor

                col.update_one(
                    {"_id": existente["_id"]},
                    {"$set": update_data}
                )

                atualizadas += 1
                continue

            serial = maquina.get("Número de Série", "")

            if serial_valido(serial):
                serial_norm = serial_normalizado(serial)

                duplicada = col.find_one({
                    "Número de Série": {
                        "$regex": f"^{serial_norm}$",
                        "$options": "i"
                    }
                })

                if duplicada:
                    tentativa_existente = tentativas.find_one({
                        "Nome da máquina": nome,
                        "Número de Série": serial,
                        "status": "pendente"
                    })

                    agora = datetime.now(timezone.utc)

                    if tentativa_existente:
                        tentativas.update_one(
                            {"_id": tentativa_existente["_id"]},
                            {
                                "$set": {
                                    "dados_maquina": maquina,
                                    "maquina_existente": duplicada.get(
                                        "Nome da máquina"
                                    ),
                                    "updated_at": agora
                                },
                                "$inc": {
                                    "quantidade_tentativas": 1
                                }
                            }
                        )
                    else:
                        tentativas.insert_one({
                            "Nome da máquina": nome,
                            "Número de Série": serial,
                            "maquina_existente": duplicada.get(
                                "Nome da máquina"
                            ),
                            "dados_maquina": maquina,
                            "status": "pendente",
                            "quantidade_tentativas": 1,
                            "created_at": agora,
                            "updated_at": agora
                        })

                    pendentes += 1
                    continue

            try:
                col.insert_one(maquina)
                inseridas += 1

            except DuplicateKeyError:
                logger.exception(
                    "Máquina já existente: %s",
                    nome
                )

        except Exception as e:
            logger.exception("Erro processando máquina")

            erros.append({
                "maquina": maquina.get("Nome da máquina"),
                "erro": str(e)
            })

    return jsonify({
        "mensagem": "Processamento concluído",
        "inseridas": inseridas,
        "atualizadas": atualizadas,
        "pendentes": pendentes,
        "erros": erros
    })


@app.route("/dados", methods=["GET"])
@basic_auth_required
def dados():
    maquinas = list(
        get_collection().find({})
    )

    return jsonify([
        serialize_document(maquina)
        for maquina in maquinas
    ])


@app.route("/tentativas_cadastro", methods=["GET"])
@basic_auth_required
def tentativas_cadastro():
    status = request.args.get(
        "status",
        "pendente"
    )

    tentativas = list(
        get_tentativas_collection()
        .find({"status": status})
        .sort("created_at", -1)
    )

    return jsonify([
        serialize_document(tentativa)
        for tentativa in tentativas
    ])


@app.route(
    "/tentativas_cadastro/<tentativa_id>/decidir",
    methods=["POST"]
)
@basic_auth_required
def decidir_tentativa(tentativa_id):
    dados = request.get_json(silent=True) or {}

    decisao = str(
        dados.get("decisao", "")
    ).lower().strip()

    if decisao not in ["aprovar", "recusar"]:
        return jsonify({
            "erro": "Decisão deve ser 'aprovar' ou 'recusar'"
        }), 400

    tentativas = get_tentativas_collection()
    col = get_collection()

    try:
        tentativa = tentativas.find_one({
            "_id": ObjectId(tentativa_id)
        })
    except Exception:
        return jsonify({
            "erro": "ID da tentativa inválido"
        }), 400

    if not tentativa:
        return jsonify({
            "erro": "Tentativa não encontrada"
        }), 404

    if tentativa.get("status") != "pendente":
        return jsonify({
            "erro": "Esta tentativa já foi decidida"
        }), 409

    agora = datetime.now(timezone.utc)

    if decisao == "recusar":
        tentativas.update_one(
            {"_id": tentativa["_id"]},
            {
                "$set": {
                    "status": "recusada",
                    "decidido_em": agora
                }
            }
        )

        return jsonify({
            "mensagem": "Tentativa recusada"
        })

    maquina = tentativa.get(
        "dados_maquina",
        {}
    )

    nome = str(
        maquina.get("Nome da máquina", "")
    ).strip()

    if not nome:
        return jsonify({
            "erro": "Máquina sem nome"
        }), 400

    existente_nome = col.find_one({
        "Nome da máquina": nome
    })

    if existente_nome:
        return jsonify({
            "erro": (
                "Já existe uma máquina com este nome. "
                "A tentativa continua pendente para evitar sobrescrever o registro."
            )
        }), 409

    try:
        col.insert_one(maquina)

    except DuplicateKeyError:
        return jsonify({
            "erro": (
                "Não foi possível aprovar porque "
                "o nome da máquina já existe."
            )
        }), 409

    tentativas.update_one(
        {"_id": tentativa["_id"]},
        {
            "$set": {
                "status": "aprovada",
                "decidido_em": agora
            }
        }
    )

    return jsonify({
        "mensagem": (
            "Tentativa aprovada e máquina adicionada "
            "ao inventário."
        )
    })


@app.route("/mongo_info", methods=["GET"])
@basic_auth_required
def mongo_info():
    col = get_collection()

    return jsonify({
        "database": db.name,
        "collection": col.name,
        "quantidade": col.count_documents({})
    })


@app.route("/editar_maquina", methods=["PUT"])
@basic_auth_required
def editar_maquina():
    dados = request.get_json(silent=True) or {}

    nome = dados.get("Nome da máquina")

    if not nome:
        return jsonify({
            "erro": "Nome da máquina não informado"
        }), 400

    campos_editaveis = [
        "Etiqueta",
        "Cidade",
        "Departamento",
        "Unidade Residente",
        "Observações"
    ]

    atualizacao = {}

    for campo in campos_editaveis:
        if campo in dados:
            atualizacao[campo] = dados[campo]

    if not atualizacao:
        return jsonify({
            "erro": "Nenhum campo editável informado"
        }), 400

    resultado = get_collection().update_one(
        {
            "Nome da máquina": nome
        },
        {
            "$set": atualizacao
        }
    )

    if resultado.matched_count == 0:
        return jsonify({
            "erro": "Máquina não encontrada"
        }), 404

    return jsonify({
        "mensagem": "Máquina atualizada"
    })


@app.route("/excluir_maquina", methods=["DELETE"])
@basic_auth_required
def excluir_maquina():
    dados = request.get_json(silent=True) or {}

    nome = dados.get("Nome da máquina")

    if not nome:
        return jsonify({
            "erro": "Nome da máquina não informado"
        }), 400

    resultado = get_collection().delete_one({
        "Nome da máquina": nome
    })

    if resultado.deleted_count == 0:
        return jsonify({
            "erro": "Máquina não encontrada"
        }), 404

    return jsonify({
        "mensagem": "Máquina excluída"
    })


if __name__ == "__main__":
    port = int(
        os.getenv("PORT", 5000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )