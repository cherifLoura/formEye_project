import groq
import base64
import json
from dotenv import load_dotenv
import os
from pydantic import create_model
from typing import Optional

load_dotenv()

client = groq.Groq(api_key=os.getenv("GROQ_API_KEY"))

def extract_form_data(image_path: str, prompt: str, schema_fields: list) -> dict:
    """
    Prend une image de formulaire et retourne les données extraites en JSON 
    validées par un modèle Pydantic généré dynamiquement.
    """

    # 1. Gestion d'erreur pour l'ouverture du fichier image
    try:
        with open(image_path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")
    except FileNotFoundError:
        print(f" Erreur : Le fichier image spécifié est introuvable : {image_path}")
        return {"error": f"Fichier image introuvable : {image_path}"}

    # Détecte le type de l'image
    extension = image_path.split(".")[-1].lower()
    media_types = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp"
    }
    media_type = media_types.get(extension, "image/jpeg")

    full_prompt = f"""
    {prompt}

    Extrais UNIQUEMENT les informations suivantes du formulaire dans l'image :
    {schema_fields}

    Réponds UNIQUEMENT avec un objet JSON valide, sans texte d'accompagnement, sans balises markdown superflues.
    Les clés du JSON doivent être exactement les éléments de cette liste : {schema_fields}

    Si un champ est absent ou illisible dans l'image, attribue-lui la valeur null.
    """

    # 2. Gestion d'erreur pour l'appel à l'API Groq
    try:
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{image_data}"
                            }
                        },
                        {
                            "type": "text",
                            "text": full_prompt
                        }
                    ]
                }
            ],
            max_tokens=1024
        )
        raw_text = response.choices[0].message.content.strip()
    except Exception as e:
        print(f" Erreur lors de l'appel à l'API Groq : {e}")
        return {"error": "Échec de la communication avec l'IA"}

    # Nettoyage des balises markdown si présentes
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
    
    raw_text = raw_text.strip()

   # 3. Sécurisation et validation DYNAMIQUE avec Pydantic
    try:
        result_dict = json.loads(raw_text)
        
        # SÉCURITÉ : Si l'IA renvoie les données imbriquées dans une clé générique
        if "data" in result_dict and isinstance(result_dict["data"], dict):
            result_dict = result_dict["data"]

        # Affichage de débogage
        print("\n--- [DEBUG] JSON reçu de l'IA ---")
        print(json.dumps(result_dict, indent=2))
        print("--- [DEBUG] Champs attendus ---")
        print(schema_fields)
        print("--------------------------------\n")
        
        # --- LA CORRECTION TECHNIQUE ICI ---
        # On importe Any pour accepter str, int, float, bool sans distinction
        from typing import Any
        fields_definition = {field: (Optional[Any], None) for field in schema_fields}
        
        # Génération du modèle dynamique Pydantic
        DynamicFormData = create_model("DynamicFormData", **fields_definition)
        
        # Alignement et nettoyage des clés demandées
        cleaned_dict = {field: result_dict.get(field) for field in schema_fields}
        
        # Validation finale
        validated_data = DynamicFormData(**cleaned_dict)
        return validated_data.model_dump()
        
    except json.JSONDecodeError:
        print(f"Erreur : L'IA n'a pas renvoye un format JSON valide.")
        return {"error": "Format JSON invalide renvoye par l'IA"}
    except Exception as e:
        print(f"Erreur lors de la validation dynamique : {str(e)}")
        return {"error": f"Erreur de validation : {str(e)}"}