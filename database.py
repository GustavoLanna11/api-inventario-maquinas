from pymongo import MongoClient
import os


# URI do Mongo vindo do Render (Environment Variable)
MONGO_URI = os.environ.get("MONGO_URI")

client = MongoClient(MONGO_URI)

# banco
db = client["inventario"]

# collection
collection = db["maquinas"]

def get_collection():
    return collection