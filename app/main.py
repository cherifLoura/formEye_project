# type: ignore
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
import shutil
import os
import uuid
import time
import json
from datetime import datetime
from typing import Dict, Tuple, List
from app.extractor import extract_form_data

# =========================================================================
# 🔐 CONFIGURATION DU RATE LIMITING (SÉCURITÉ ANTI-DOS)
# =========================================================================
# Header HTTP où l'utilisateur transmet sa clé (ex: X-API-Key: ma_cle_premium)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

# Base de données fictive des clés d'API valides (À coupler avec une vraie DB à terme)
USER_DATABASE = {
    "cle_standard_demo": {"tier": "standard", "owner": "Utilisateur Standard (Chérif)"},
    "cle_premium_demo": {"tier": "premium", "owner": "Entreprise Premium (FormEye Corp)"}
}

# Définition stricte des quotas par catégorie d'utilisateur
QUOTAS = {
    "standard": {"per_second": 2, "per_day": 100},
    "premium": {"per_second": 10, "per_day": 5000}
}

# Historique en mémoire locale (Structure : {cle_api: ([timestamps_seconde], [timestamps_jour])})
# Note de production : Dans un environnement multi-conteneurs, ce dictionnaire serait remplacé par Redis.
RATE_LIMIT_STORE: Dict[str, Tuple[List[float], List[float]]] = {}

def verify_rate_limits(api_key: str = Depends(api_key_header)) -> dict:
    """
    Dépendance de sécurité interceptant les requêtes.
    Valide l'existence de la clé d'API et applique les algorithmes de fenêtre glissante.
    """
    # 1. Authentification de la clé
    if api_key not in USER_DATABASE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clé d'API invalide, expirée ou manquante dans les entêtes."
        )
        
    user_info = USER_DATABASE[api_key]
    tier = user_info["tier"]
    limits = QUOTAS[tier]
    current_time = time.time()
    
    # Initialisation des compteurs pour cette clé si première requête
    if api_key not in RATE_LIMIT_STORE:
        RATE_LIMIT_STORE[api_key] = ([], [])
        
    sec_history, day_history = RATE_LIMIT_STORE[api_key]
    
    # 2. Algorithme de fenêtre glissante : Nettoyage des historiques obsolètes
    sec_history = [t for t in sec_history if current_time - t < 1.0]      # 1 seconde glissante
    day_history = [t for t in day_history if current_time - t < 86400.0]  # 24 heures glissantes
    
    # Sauvegarde du nettoyage
    RATE_LIMIT_STORE[api_key] = (sec_history, day_history)
    
    # 3. Contrôle des Quotas instantanés (Par seconde)
    if len(sec_history) >= limits["per_second"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Débit maximal par seconde dépassé pour la catégorie '{tier}'. Limite : {limits['per_second']}/s."
        )
        
    # 4. Contrôle des Quotas journaliers (Par jour)
    if len(day_history) >= limits["per_day"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Quota d'appels journalier épuisé pour la catégorie '{tier}'. Limite : {limits['per_day']}/jour."
        )
        
    # Validation réussie : enregistrement du timestamp actuel
    sec_history.append(current_time)
    day_history.append(current_time)
    
    return user_info


# =========================================================================
# 🚀 INITIALISATION DE L'APPLICATION FASTAPI
# =========================================================================
app = FastAPI(
    title="FormEye API",
    description="Pipeline sécurisé d'extraction de données de formulaires avec contrôle de débit",
    version="1.1.0"
)

BASE_UPLOAD_DIR = "formEye_uploads"

# CONFIGURATION DES LIMITES DE SÉCURITÉ DES FICHIERS
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 Mo


@app.get("/")
def read_root():
    return {"status": "success", "message": "Hi Cherif Loura, le serveur FormEye est opérationnel !"}


@app.post("/extract")
async def extract_form(
    image: UploadFile = File(...),
    prompt: str = Form(...), 
    fields: str = Form(...),
    current_user: dict = Depends(verify_rate_limits) # <--- INJECTION DE LA BARRIÈRE ANTI-DOS 🛡️
):
    """
    Endpoint d'extraction de formulaires. Protégé par clé d'API (Standard/Premium),
    soumis à une limitation stricte des requêtes et à une validation de charge utile.
    """
    try:
        # =========================================================================
        # 🛡️ BARRIÈRE 1 : SÉCURITÉ DU TYPE, DE L'EXTENSION ET DU TYPE MIME
        # =========================================================================
        file_extension = os.path.splitext(image.filename)[1].lower()
        
        if file_extension not in ALLOWED_EXTENSIONS or image.content_type not in ALLOWED_MIME_TYPES:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "status": "error",
                    "code": "INVALID_FILE_TYPE",
                    "message": f"Le format {file_extension} ({image.content_type}) n'est pas supporté. Extensions valides : PNG, JPG, JPEG, WEBP."
                }
            )

        # =========================================================================
        # 🛡️ BARRIÈRE 2 : VÉRIFICATION STRICTE DE LA TAILLE DU FICHIER (Anti-saturation disque)
        # =========================================================================
        # Lecture de la taille réelle du flux d'octets en mémoire tampon
        image.file.seek(0, os.SEEK_END)
        file_size = image.file.tell()
        image.file.seek(0) # Réinitialisation du curseur de lecture pour la copie ultérieure
        
        if file_size > MAX_FILE_SIZE:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={
                    "status": "error",
                    "code": "FILE_TOO_LARGE",
                    "message": f"Le fichier dépasse la limite autorisée de 5 Mo. Taille reçue : {file_size / (1024*1024):.2f} Mo."
                }
            )

        # =========================================================================
        # 🗂️ TRAITEMENT & STOCKAGE CHRONOLOGIQUE PAR DATE
        # =========================================================================
        date_folder = datetime.now().strftime("%Y-%m-%d")
        upload_dir_path = os.path.join(BASE_UPLOAD_DIR, date_folder)
        os.makedirs(upload_dir_path, exist_ok=True)
        
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(upload_dir_path, unique_filename)
        
        # Copie sécurisée du stream sur l'espace persistant
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
            
        # Désérialisation de la chaîne de caractères issue du FormData en liste
        schema_fields = [f.strip() for f in fields.split(",") if f.strip()]
        
        # Exécution de la logique métier d'extraction via LLM Vision
        extracted_json = extract_form_data(
            image_path=file_path,
            prompt=prompt,
            schema_fields=schema_fields
        )
        
        if isinstance(extracted_json, dict) and "error" in extracted_json:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"status": "error", "message": extracted_json["error"]}
            )
        
        # Réponse structurée enrichie avec les métadonnées de consommation de l'appelant
        return {
            "status": "success",
            "api_user": current_user["owner"],
            "tier_level": current_user["tier"],
            "original_filename": image.filename,
            "saved_filename": unique_filename,
            "storage_path": file_path,
            "data": extracted_json
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "message": f"Exception critique sur le serveur : {str(e)}"}
        )