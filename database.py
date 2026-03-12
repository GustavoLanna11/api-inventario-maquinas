import sqlite3

conn = sqlite3.connect("inventario.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS maquinas (
    "Nome da máquina" TEXT,
    "Proprietário" TEXT,
    "Etiqueta" TEXT,
    "Cidade" TEXT,
    "Departamento" TEXT,
    "Unidade Residente" TEXT,
    "Marca" TEXT,
    "Número de Série" TEXT,
    "Tipo" TEXT,
    "Modelo" TEXT,
    "Licença" TEXT,
    "Processador" TEXT,
    "Troca de máquina" TEXT,
    "Tipo de memória" TEXT,
    "Pentes" TEXT,
    "Tamanho" REAL,
    "Armazenamento" REAL,
    "Tipo de armazenamento" TEXT,
    "Licença Windows" TEXT,
    "Troca ou Upgrade" TEXT,
    "Prioridade" TEXT,
    "Antivírus" TEXT,
    "Upgrade?" TEXT,
    "Em uso?" TEXT,
    "Está no AD?" TEXT,
    "Observações" TEXT
)
""")

conn.commit()