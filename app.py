from flask import Flask, request, jsonify, Response
import os
from werkzeug.utils import secure_filename
import pandas as pd
import json
import numpy as np
from database import get_collection

app = Flask(__name__)

collection = get_collection()

# Caminhos absolutos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route("/upload_excel", methods=["POST"])
def upload_excel():
    if "file" not in request.files:
        return jsonify({"error": "Arquivo não encontrado"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "Nome do arquivo está vazio"}), 400

    if not file.filename.lower().endswith(".xlsx"):
        return jsonify({"error": "Envie um arquivo .xlsx"}), 400

    try:
        temp_path = os.path.join(UPLOAD_FOLDER, secure_filename(file.filename))
        file.save(temp_path)
        print(f"📥 Arquivo salvo temporariamente em: {temp_path}")

        df_recebido = pd.read_excel(temp_path)

        # Limpar NaN
        df_recebido = df_recebido.replace({np.nan: None})
        dados = df_recebido.to_dict("records")

        for doc in dados:
            # Usar Número de Série se existir, senão Nome da máquina
            filtro = {}
            if doc.get("Número de Série"):
                filtro = {"Número de Série": doc["Número de Série"]}
            else:
                filtro = {"Nome da máquina": doc.get("Nome da máquina", "")}

            # Atualiza se existir, insere se não existir
            collection.update_one(filtro, {"$set": doc}, upsert=True)

        os.remove(temp_path)

        return jsonify({"message": "✅ Dados inseridos/atualizados no MongoDB!"})

    except Exception as e:
        print(f"❌ Erro upload: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/dados", methods=["GET"])
def listar_dados():
    try:
        dados = list(collection.find({}, {"_id": 0}))
        json_str = json.dumps(dados, ensure_ascii=False)
        return Response(json_str, mimetype="application/json")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/mongo_info", methods=["GET"])
def mongo_info():
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
    print("🚀 API rodando com MongoDB")
    app.run(host="0.0.0.0", port=port)