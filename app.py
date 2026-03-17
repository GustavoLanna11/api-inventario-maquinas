from flask import Flask, request, jsonify, Response
import os
import json
from database import get_collection

app = Flask(__name__)

collection = get_collection()


@app.route("/upload_excel", methods=["POST"])
def upload_excel():
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "JSON não enviado"}), 400

        # garante lista
        if isinstance(data, dict):
            data = [data]

        for doc in data:

            if doc.get("Número de Série"):
                filtro = {"Número de Série": doc["Número de Série"]}
            else:
                filtro = {"Nome da máquina": doc.get("Nome da máquina", "")}

            collection.update_one(filtro, {"$set": doc}, upsert=True)

        print("📦 Dados recebidos:", data)

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
    print("🚀 API rodando com MongoDB (modo JSON)")
    app.run(host="0.0.0.0", port=port)