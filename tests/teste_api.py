import requests

url = "http://localhost:5000/dados"  # Altere aqui se estiver rodando em outro IP
response = requests.get(url)

print("Status code:", response.status_code)
print("Content-Type:", response.headers.get("Content-Type"))
try:
    data = response.json()
    print("✅ JSON carregado com sucesso!")
    print("Exemplo de dados:", data[:2])  # Mostra os 2 primeiros registros
except Exception as e:
    print("❌ Erro ao parsear JSON:", e)
    print("Resposta bruta (primeiras 500 chars):", response.text[:500])
