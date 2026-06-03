from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
import shutil
import os
import uuid  # <-- Importation indispensable pour générer des identifiants uniques (UUID)
from app.extractor import extract_form_data

app = FastAPI(
    title="FormEye API",
    description="Pipeline d'extraction de données de formulaires",
    version="1.0.0"
)

# Configuration du dossier pour stocker les images reçues
UPLOAD_DIR = "images"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.get("/")
def read_root():
    return {"status": "success", "message": "Le serveur FormEye est opérationnel !"}

@app.post("/extract")
async def extract_form(
    image: UploadFile = File(...), 
    prompt: str = Form(...), 
    fields: str = Form(...)
):
    """
    Endpoint principal (POST) : Reçoit une image, un prompt et une liste de champs,
    génère un nom de fichier unique (UUID), le sauvegarde localement, 
    puis extrait les données via l'IA avec un schéma dynamique.
    """
    try:
        # 1. Extraire l'extension d'origine du fichier (ex: .png, .jpg)
        file_extension = os.path.splitext(image.filename)[1]
        
        # 2. Générer un nom unique universel (UUID) pour éviter les collisions
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        
        # 3. Définir le chemin de sauvegarde sécurisé avec le nom unique
        file_path = os.path.join(UPLOAD_DIR, unique_filename)
        
        # 4. Écrire le fichier image sur le disque
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
            
        # 5. Transformer la chaîne "fields" en une vraie liste Python
        schema_fields = [f.strip() for f in fields.split(",") if f.strip()]
        
        # 6. Appeler l'extracteur dynamique développé en Semaine 2
        extracted_json = extract_form_data(
            image_path=file_path,
            prompt=prompt,
            schema_fields=schema_fields
        )
        
        # 7. Si l'extracteur renvoie une erreur interne (ex: échec IA ou validation)
        if isinstance(extracted_json, dict) and "error" in extracted_json:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": extracted_json["error"]}
            )
        
        # 8. Retourner le résultat final avec le suivi des noms de fichiers
        return {
            "status": "success",
            "original_filename": image.filename,
            "saved_filename": unique_filename,
            "data": extracted_json
        }
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Une erreur est survenue sur le serveur : {str(e)}"}
        )