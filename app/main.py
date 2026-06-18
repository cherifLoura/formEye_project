# type: ignore
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
import shutil #-- Importation de la bibliothèque shutil pour gérer les opérations de fichiers, notamment la copie de fichiers. Dans ce contexte, shutil.copyfileobj() est utilisé pour copier le contenu du fichier téléchargé (image) vers un emplacement de stockage local de manière efficace et sécurisée.
import os   #-- Importation de la bibliothèque os pour interagir avec le système d'exploitation, notamment pour gérer les chemins de fichiers et les opérations de création de répertoires. Dans ce code, os.makedirs() est utilisé pour créer le répertoire de stockage des images s'il n'existe pas déjà, et os.path.join() est utilisé pour construire des chemins de fichiers de manière sécurisée et compatible avec différents systèmes d'exploitation.
import uuid  # <-- Importation indispensable pour générer des identifiants uniques (UUID)
from datetime import datetime  # <-- Ajouté pour le partitionnement chronologique du stockage local
from app.extractor import extract_form_data

#-- création de l'interface de l'API avec FastAPI
    #-- création de l'entête de l'API avec un titre, une description et une version
        #-- Nb: FastAPI est un framework web moderne et rapide pour construire des APIs avec Python 3.7+ basé sur les annotations de type standard de Python. Il est conçu pour être facile à utiliser et à apprendre, tout en étant performant et robuste. FastAPI utilise Pydantic pour la validation des données et Starlette pour la gestion des requêtes et des réponses HTTP.
            #-- FastAPI est une classe et app est une instance de cette classe. En créant une instance de FastAPI, nous définissons notre application web et pouvons ensuite ajouter des routes (endpoints) pour gérer les différentes requêtes HTTP que notre API recevra. L'instance app est le point d'entrée principal de notre application FastAPI, et c'est à travers elle que nous allons définir nos routes, gérant les requêtes et les réponses, et configurer les fonctionnalités de notre API.
app = FastAPI(

        title="FormEye API",
        description="Pipeline d'extraction de données de formulaires",
        version="1.0.0"
)

# Configuration du dossier racine pour stocker les images reçues
BASE_UPLOAD_DIR = "formEye_uploads"

# CONFIGURATION DES LIMITES DE SÉCURITÉ (Robustesse)
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}  # Les deux sont des structures de type set
ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"} #complètement indépendant de l'extension du fichier, le type MIME est une information transmise par le client (navigateur ou application) qui indique le type de contenu du fichier. Il est important de vérifier à la fois l'extension et le type MIME pour s'assurer que le fichier est bien une image valide et éviter les attaques par téléchargement de fichiers malveillants.
MAX_FILE_SIZE = 5 * 1024 * 1024  # Limite stricte : 5 Mo en octets

@app.get("/")
def read_root():
    return {"status": "success", "message": "Hi Cherif Loura, le serveur FormEye est opérationnel !"}

   #----- endpoint POST pour recevoir une image, un prompt et une liste de champs, puis extraire les données du formulaire -----
@app.post("/extract")
async def extract_form(
    image: UploadFile = File(...),  #type special de FastAPI pour les fichiers uploadés
    prompt: str = Form(...), 
    fields: str = Form(...)
):
    """
    Endpoint principal (POST) : Reçoit une image, un prompt et une liste de champs,
    génère un nom de fichier unique (UUID), le sauvegarde localement dans un dossier daté, 
    puis extrait les données via l'IA avec un schéma dynamique.
    """
    try:
        # =========================================================================
        # 🛡️ BARRIÈRE 1 & 2 : SÉCURITÉ DU TYPE, DE L'EXTENSION ET DU TYPE MIME
        # =========================================================================
        # Extraire l'extension d'origine du fichier (ex: .png, .jpg) convertie en minuscules
        file_extension = os.path.splitext(image.filename)[1].lower()
        
        # Validation croisée de l'extension et du type MIME communiqué par le client
        if file_extension not in ALLOWED_EXTENSIONS or image.content_type not in ALLOWED_MIME_TYPES:
            return JSONResponse(
                status_code=400,
                content={

                    "status": "error",
                    "code": "INVALID_FILE_TYPE",
                    "message": f"Le format {file_extension} ({image.content_type}) n'est pas supporté. Veuillez envoyer une image valide (PNG, JPG, JPEG ou WEBP)."
                }
            )

    
        # =========================================================================
        # 🗂️ TRAITEMENT & STOCKAGE GÉOLOCALISÉ PAR DATE (Robustesse)
        # =========================================================================
        # 1. Obtenir la date courante pour organiser les sous-dossiers (Format : AAAA-MM-JJ)
        date_folder = datetime.now().strftime("%Y-%m-%d")
        
        # 2. Construire le chemin du répertoire du jour (ex: formEye_uploads/2026-06-08)
        upload_dir_path = os.path.join(BASE_UPLOAD_DIR, date_folder)
        os.makedirs(upload_dir_path, exist_ok=True)
        
        # 3. Générer un nom unique universel (UUID) pour éviter les collisions
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        
        # 4. Définir le chemin de sauvegarde complet final
        file_path = os.path.join(upload_dir_path, unique_filename)
        
        # Écrire le fichier image sur le disque
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
            
        # Transformer la chaîne "fields" en une vraie liste Python
        schema_fields = [f.strip() for f in fields.split(",") if f.strip()]
        
        # Appeler l'extracteur dynamique en passant le chemin de l'image, le prompt et les champs du schéma dynamique
        extracted_json = extract_form_data(
            image_path=file_path,
            prompt=prompt,
            schema_fields=schema_fields
        )
        
        # Si l'extracteur renvoie une erreur interne (ex: échec IA ou validation)
        if isinstance(extracted_json, dict) and "error" in extracted_json:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": extracted_json["error"]}
            )
        
        # Retourner le résultat final avec le suivi des noms de fichiers
        return {
            "status": "success",
            "original_filename": image.filename,
            "saved_filename": unique_filename,
            "storage_path": file_path,
            "data": extracted_json
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()  # Affiche la trace complète de l'erreur dans la console pour le débogage
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Une erreur est survenue sur le serveur : {str(e)}"}
        )