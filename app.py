from flask import Flask, request, jsonify, Response
import os
import json
import re
from base64 import b64decode
from datetime import datetime, timezone
from bson import ObjectId
from database import get_collection
from pymongo.errors import DuplicateKeyError

app = Flask(__name__)

# Token vindo do ambiente (Render)
SECRET_TOKEN = os.environ.get("API_SECRET_TOKEN")

collection = get_collection()

# Coleção separada para tentativas de cadastro duplicadas
tentativas_collection = collection.database["tentativas_cadastro"]

try:
    collection.create_index("Nome da máquina", unique=True)
    print("🔒 Índice único criado para 'Nome da máquina'")
except Exception as e:
    print(f"⚠️ Índice já existe ou erro ao criar: {e}")


# ==========================
# HEALTH CHECK
# ==========================

@app.route("/health", methods=["GET"])
def health():
    try:
        total = collection.count_documents({})
        return jsonify({
            "status": "ok",
            "service": "api-inventario",
            "mongo": "connected",
            "documentos": total
        }), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "service": "api-inventario",
            "mongo": "disconnected",
            "error": str(e)
        }), 500


# ==========================
# AUTENTICAÇÃO BASIC AUTH
# ==========================

def validar_login():
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Basic "):
        return False, Response(
            "Login necessário",
            401,
            {"WWW-Authenticate": 'Basic realm="Login Required"'}
        )

    try:
        encoded = auth_header.split(" ", 1)[1]
        decoded = b64decode(encoded).decode("utf-8")
        username, password = decoded.split(":", 1)

        if (
            username == os.environ.get("API_USER")
            and password == os.environ.get("API_PASSWORD")
        ):
            return True, None

    except Exception:
        pass

    return False, Response(
        "Credenciais inválidas",
        401,
        {"WWW-Authenticate": 'Basic realm="Login Required"'}
    )


# ==========================
# NORMALIZAÇÃO DE NÚMERO DE SÉRIE
# ==========================

SERIAIS_INVALIDOS = {
    "",
    "não encontrado",
    "nao encontrado",
    "filled by oem",
    "to be filled by o.e.m.",
    "to be filled by oem",
    "default string",
    "unknown",
    "none",
    "null",
    "n/a",
    "na"
}


def normalizar_serial(valor):
    if valor is None:
        return ""

    serial = str(valor).strip()

    if serial.casefold() in SERIAIS_INVALIDOS:
        return ""

    return serial


# ==========================
# CONTROLE DE TENTATIVAS DUPLICADAS
# ==========================

def agora_utc():
    return datetime.now(timezone.utc)


def serial_existente(serial):
    return collection.find_one({
        "Número de Série": {
            "$regex": r"^\s*" + re.escape(serial) + r"\s*$",
            "$options": "i"
        }
    })


def salvar_tentativa_duplicada(doc, serial, maquina_existente):
    agora = agora_utc()

    filtro = {
        "Nome da máquina": doc["Nome da máquina"],
        "Número de Série": serial,
        "status": "pendente"
    }

    dados_maquina = dict(doc)
    dados_maquina.pop("_id", None)

    tentativa = tentativas_collection.find_one(filtro)

    if tentativa:
        tentativas_collection.update_one(
            {"_id": tentativa["_id"]},
            {
                "$set": {
                    "dados_maquina": dados_maquina,
                    "maquina_existente": maquina_existente,
                    "ultima_tentativa": agora
                },
                "$inc": {
                    "quantidade_tentativas": 1
                }
            }
        )

    else:
        tentativas_collection.insert_one({
            "Nome da máquina": doc["Nome da máquina"],
            "Número de Série": serial,
            "maquina_existente": maquina_existente,
            "dados_maquina": dados_maquina,
            "status": "pendente",
            "criada_em": agora,
            "ultima_tentativa": agora,
            "quantidade_tentativas": 1
        })


# ==========================
# UPLOAD DO AGENTE GPO
# ==========================

@app.route("/upload_excel", methods=["POST"])
def upload_excel():
    token = request.headers.get("Authorization")

    if not SECRET_TOKEN:
        return jsonify({
            "error": "Token não configurado na API"
        }), 500

    if token != f"Bearer {SECRET_TOKEN}":
        return jsonify({"error": "Não autorizado"}), 401

    try:
        data = request.get_json(silent=True)

        if not data:
            return jsonify({"error": "JSON não enviado"}), 400

        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list):
            return jsonify({
                "error": "O JSON deve ser um objeto ou uma lista de objetos"
            }), 400

        campos_preservados = [
            "Etiqueta",
            "Cidade",
            "Departamento",
            "Unidade Residente",
            "Observações"
        ]

        cadastradas = 0
        atualizadas = 0
        ignoradas = []

        for doc_original in data:

            if not isinstance(doc_original, dict):
                return jsonify({
                    "error": "Cada máquina deve ser um objeto JSON"
                }), 400

            doc = doc_original.copy()
            nome_maquina = doc.get("Nome da máquina")

            if not isinstance(nome_maquina, str) or not nome_maquina.strip():
                return jsonify({
                    "error": "Nome da máquina é obrigatório"
                }), 400

            nome_maquina = nome_maquina.strip()
            doc["Nome da máquina"] = nome_maquina

            serial = normalizar_serial(doc.get("Número de Série"))

            # Procura primeiro pelo nome da máquina.
            maquina_existente = collection.find_one({
                "Nome da máquina": nome_maquina
            })

            if maquina_existente:
                # Máquina existente: mantém os dados antigos
                # e atualiza os campos técnicos enviados pelo agente.
                documento_final = maquina_existente.copy()
                documento_final.update(doc)

                # Não permite que o agente sobrescreva
                # os campos administrativos do dashboard.
                for campo in campos_preservados:
                    documento_final[campo] = maquina_existente.get(campo)

                # Se o agente enviar serial vazio ou inválido,
                # preserva um serial válido já cadastrado.
                serial_antigo = normalizar_serial(
                    maquina_existente.get("Número de Série")
                )

                if not serial and serial_antigo:
                    documento_final["Número de Série"] = (
                        maquina_existente["Número de Série"]
                    )

                try:
                    collection.update_one(
                        {"_id": maquina_existente["_id"]},
                        {"$set": {
                            chave: valor
                            for chave, valor in documento_final.items()
                            if chave != "_id"
                        }}
                    )
                except DuplicateKeyError:
                    return jsonify({
                        "error": "Conflito de duplicidade ao atualizar",
                        "maquina": nome_maquina
                    }), 409

                atualizadas += 1
                print(f"🔄 Máquina atualizada: {nome_maquina}")
                continue

            # Máquina nova: verifica se o serial válido
            # já pertence a outro registro.
            if serial:
                registro_serial = serial_existente(serial)

                if registro_serial:
                    salvar_tentativa_duplicada(
                        doc=doc,
                        serial=serial,
                        maquina_existente=registro_serial.get(
                            "Nome da máquina",
                            "Desconhecida"
                        )
                    )

                    print(
                        f"⏳ Tentativa pendente: {nome_maquina}; "
                        f"serial já pertence a "
                        f"{registro_serial.get('Nome da máquina', 'Desconhecida')}."
                    )
                    continue

            # Máquina nova sem serial duplicado.
            # Seriais vazios ou inválidos não bloqueiam o cadastro.
            try:
                collection.insert_one(doc)
                cadastradas += 1
                print(f"✅ Máquina cadastrada: {nome_maquina}")

            except DuplicateKeyError:
                # Proteção adicional para concorrência
                # e índice único pelo nome da máquina.
                ignoradas.append({
                    "Nome da máquina": nome_maquina,
                    "Número de Série": serial,
                    "Motivo": "Nome da máquina já cadastrado"
                })

        return jsonify({
            "message": "Processamento do inventário concluído",
            "máquinas_cadastradas": cadastradas,
            "máquinas_atualizadas": atualizadas,
            "máquinas_ignoradas_por_duplicidade": len(ignoradas),
            "detalhes_duplicidades": ignoradas
        }), 200

    except Exception as e:
        print(f"❌ Erro upload: {e}")

        return jsonify({
            "error": str(e)
        }), 500


# ==========================
# LISTAR MÁQUINAS
# ==========================

@app.route("/dados", methods=["GET"])
def listar_dados():
    autorizado, erro = validar_login()

    if not autorizado:
        return erro

    try:
        dados = list(collection.find({}, {"_id": 0}))
        json_str = json.dumps(dados, ensure_ascii=False, allow_nan=False)

        return Response(
            json_str,
            mimetype="application/json"
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================
# LISTAR TENTATIVAS DE CADASTRO
# ==========================

@app.route("/tentativas_cadastro", methods=["GET"])
def listar_tentativas_cadastro():
    autorizado, erro = validar_login()

    if not autorizado:
        return erro

    status = request.args.get("status", "pendente")

    if status not in {"pendente", "aprovada", "recusada"}:
        return jsonify({"error": "Status inválido"}), 400

    try:
        tentativas = list(
            tentativas_collection.find({
                "status": status
            }).sort("ultima_tentativa", -1)
        )

        resultado = []

        for tentativa in tentativas:
            resultado.append({
                "_id": str(tentativa["_id"]),
                "id": str(tentativa["_id"]),
                "Nome da máquina": tentativa.get(
                    "Nome da máquina", ""
                ),
                "Número de Série": tentativa.get(
                    "Número de Série", ""
                ),
                "maquina_existente": tentativa.get(
                    "maquina_existente", ""
                ),
                "dados_maquina": tentativa.get(
                    "dados_maquina", {}
                ),
                "status": tentativa.get("status", "pendente"),
                "criada_em": (
                    tentativa["criada_em"].isoformat()
                    if tentativa.get("criada_em") else None
                ),
                "ultima_tentativa": (
                    tentativa["ultima_tentativa"].isoformat()
                    if tentativa.get("ultima_tentativa") else None
                ),
                "quantidade_tentativas": tentativa.get(
                    "quantidade_tentativas", 1
                )
            })

        return jsonify(resultado), 200

    except Exception as e:
        print(f"❌ Erro ao listar tentativas: {e}")

        return jsonify({
            "error": "Erro ao listar tentativas"
        }), 500


# ==========================
# APROVAR OU RECUSAR TENTATIVA
# ==========================

@app.route(
    "/tentativas_cadastro/<tentativa_id>/decidir",
    methods=["POST"]
)
def decidir_tentativa_cadastro(tentativa_id):
    autorizado, erro = validar_login()

    if not autorizado:
        return erro

    try:
        tentativa_oid = ObjectId(tentativa_id)

    except Exception:
        return jsonify({
            "error": "ID de tentativa inválido"
        }), 400

    dados = request.get_json(silent=True) or {}
    decisao = dados.get("decisao")

    if decisao not in {"aprovar", "recusar"}:
        return jsonify({
            "error": "A decisão deve ser 'aprovar' ou 'recusar'"
        }), 400

    tentativa = tentativas_collection.find_one({
        "_id": tentativa_oid,
        "status": "pendente"
    })

    if not tentativa:
        return jsonify({
            "error": "Tentativa não encontrada ou já decidida"
        }), 404

    agora = agora_utc()

    # Recusar: não insere a máquina e mantém o histórico.
    if decisao == "recusar":
        resultado = tentativas_collection.update_one(
            {
                "_id": tentativa_oid,
                "status": "pendente"
            },
            {
                "$set": {
                    "status": "recusada",
                    "decidida_em": agora,
                    "decisao_por": "dashboard"
                }
            }
        )

        if resultado.modified_count == 0:
            return jsonify({
                "error": "A tentativa já foi decidida"
            }), 409

        return jsonify({
            "message": "Tentativa recusada"
        }), 200

    # Aprovar: permite o serial duplicado,
    # mas não permite duplicar o nome da máquina.
    doc = dict(tentativa.get("dados_maquina") or {})
    doc.pop("_id", None)

    nome_maquina = doc.get("Nome da máquina")

    if not isinstance(nome_maquina, str) or not nome_maquina.strip():
        return jsonify({
            "error": "Dados da máquina inválidos na tentativa"
        }), 400

    nome_maquina = nome_maquina.strip()
    doc["Nome da máquina"] = nome_maquina

    if collection.find_one({
        "Nome da máquina": nome_maquina
    }):
        return jsonify({
            "error": (
                "Já existe uma máquina com esse nome no inventário. "
                "A tentativa continua pendente."
            )
        }), 409

    try:
        collection.insert_one(doc)

    except DuplicateKeyError:
        return jsonify({
            "error": (
                "Não foi possível aprovar: já existe uma máquina "
                "com esse nome. A tentativa continua pendente."
            )
        }), 409

    resultado = tentativas_collection.update_one(
        {
            "_id": tentativa_oid,
            "status": "pendente"
        },
        {
            "$set": {
                "status": "aprovada",
                "decidida_em": agora,
                "decisao_por": "dashboard",
                "maquina_inserida": nome_maquina
            }
        }
    )

    return jsonify({
        "message": (
            f"Máquina {nome_maquina} cadastrada com sucesso. "
            "O registro anterior foi mantido."
        )
    }), 200


# ==========================
# INFORMAÇÕES DO MONGODB
# ==========================

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
        }), 200

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


# ==========================
# EDITAR MÁQUINA
# ==========================

@app.route("/editar_maquina", methods=["PUT"])
def editar_maquina():
    autorizado, erro = validar_login()

    if not autorizado:
        return erro

    try:
        dados = request.get_json(silent=True)

        if not isinstance(dados, dict):
            return jsonify({
                "error": "JSON inválido"
            }), 400

        nome_maquina = dados.get("Nome da máquina")

        if not isinstance(nome_maquina, str) or not nome_maquina.strip():
            return jsonify({
                "error": "Nome da máquina não informado"
            }), 400

        # Converte NaN e Infinity em None.
        for chave, valor in dados.items():
            if isinstance(valor, float):
                if valor != valor or valor in (float("inf"), float("-inf")):
                    dados[chave] = None

        campos_editaveis = {
            campo: dados[campo]
            for campo in [
                "Etiqueta",
                "Cidade",
                "Departamento",
                "Unidade Residente",
                "Observações"
            ]
            if campo in dados
        }

        if not campos_editaveis:
            return jsonify({
                "error": "Nenhum campo editável foi enviado"
            }), 400

        resultado = collection.update_one(
            {"Nome da máquina": nome_maquina.strip()},
            {"$set": campos_editaveis}
        )

        if resultado.matched_count == 0:
            return jsonify({
                "error": "Máquina não encontrada"
            }), 404

        return jsonify({
            "message": "Máquina atualizada com sucesso"
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================
# EXCLUIR MÁQUINA
# ==========================

@app.route("/excluir_maquina", methods=["DELETE"])
def excluir_maquina():
    autorizado, erro = validar_login()

    if not autorizado:
        return erro

    try:
        dados = request.get_json(silent=True) or {}
        nome_maquina = dados.get("Nome da máquina")

        if not isinstance(nome_maquina, str) or not nome_maquina.strip():
            return jsonify({
                "error": "Nome da máquina não informado"
            }), 400

        nome_maquina = nome_maquina.strip()

        resultado = collection.delete_one({
            "Nome da máquina": nome_maquina
        })

        if resultado.deleted_count == 0:
            return jsonify({
                "error": "Máquina não encontrada"
            }), 404

        return jsonify({
            "message": f"Máquina {nome_maquina} excluída com sucesso"
        }), 200

    except Exception as e:
        print(f"❌ Erro ao excluir máquina: {e}")

        return jsonify({
            "error": "Erro interno ao excluir a máquina"
        }), 500


# ==========================
# EXECUÇÃO
# ==========================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("🚀 API rodando com MongoDB (modo JSON)")
    app.run(host="0.0.0.0", port=port)