from flask import Flask, request, jsonify, Response, json
import os
from werkzeug.utils import secure_filename
import pandas as pd

app = Flask(__name__)

# 🧭 Caminhos absolutos para garantir que salva corretamente
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
DATA_FOLDER = os.path.join(BASE_DIR, "data")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DATA_FOLDER, exist_ok=True)

PLANILHA_FINAL = os.path.join(DATA_FOLDER, "dados_gerais.xlsx")

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
        # 🔄 Salva temporariamente o arquivo
        temp_path = os.path.join(UPLOAD_FOLDER, secure_filename(file.filename))
        file.save(temp_path)
        print(f"📥 Arquivo salvo temporariamente em: {temp_path}")

        # 📊 Lê os dados recebidos
        df_recebido = pd.read_excel(temp_path)

        # 🗃 Junta ou cria planilha final
        if os.path.exists(PLANILHA_FINAL):
            df_atual = pd.read_excel(PLANILHA_FINAL)
            df_unido = pd.concat([df_atual, df_recebido], ignore_index=True)
        else:
            df_unido = df_recebido

        # 💾 Salva corretamente dentro de /data
        df_unido.to_excel(PLANILHA_FINAL, index=False)
        print(f"✅ Planilha final salva em: {PLANILHA_FINAL}")

        # 🧹 Remove o temporário
        os.remove(temp_path)

        return jsonify({"message": "✅ Dados adicionados com sucesso!"}), 200

    except Exception as e:
        return jsonify({"error": f"Erro ao processar: {e}"}), 500


@app.route("/dados", methods=["GET"])
def listar_dados():
    if not os.path.exists(PLANILHA_FINAL):
        return jsonify({"error": "Arquivo de dados não encontrado"}), 404

    try:
        df = pd.read_excel(PLANILHA_FINAL)
        dados_json = df.to_dict(orient="records")
        return Response(json.dumps(dados_json, ensure_ascii=False, indent=2), mimetype='application/json')
    except Exception as e:
        return jsonify({"error": f"Erro ao ler a planilha: {e}"}), 500


if __name__ == "__main__":
    print(f"🚀 API rodando — salvando planilha final em: {PLANILHA_FINAL}")
    app.run(host="0.0.0.0", port=5000)
