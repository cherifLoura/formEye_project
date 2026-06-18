# type: ignore
import groq
import base64
import json
from dotenv import load_dotenv
import os
import re  # <-- Indispensable pour extraire le JSON par Regex de manière robuste
import uuid  # <-- Ajouté pour garantir l'unicité des namespaces de modèles Pydantic
from pydantic import create_model
from typing import Optional, Any, Dict

load_dotenv()

# Initialisation sécurisée du client Groq
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise ValueError("La variable d'environnement GROQ_API_KEY est manquante.")

client = groq.Groq(api_key=api_key)

def clean_json_string(raw_text: str) -> str:
    """
    Nettoie de manière robuste la réponse textuelle de l'IA pour n'extraire
    que la chaîne JSON valide, même en présence de texte d'accompagnement ou de markdown.
    """
    text = raw_text.strip()
    
    # Stratégie 1 : Extraction par Expression Régulière du premier bloc {...} ou [...] de manière NON-GLOUTONNE (.*?)
    match = re.search(r"(\{.*?\}|\[.*?\])", text, re.DOTALL)
    if match:
        text = match.group(1)
    else:
        # Si aucune accolade n'est isolée, on applique le nettoyage classique du markdown au cas où
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            
    return text.strip()

def normalize_dict_keys(d: dict) -> dict:
    """
    Normalise toutes les clés d'un dictionnaire en minuscules, sans espaces ni tirets,
    pour éliminer les faux négatifs lors de l'alignement avec le schéma.
    """
    if not isinstance(d, dict):
        return {}
    return {str(k).strip().lower().replace(" ", "").replace("_", "").replace("-", ""): v for k, v in d.items()}

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

    # Amélioration du prompt système pour forcer l'alignement strict du schéma
    full_prompt = f"""
    {prompt}

    Extrais UNIQUEMENT les informations suivantes du formulaire dans l'image :
    {schema_fields}

    Réponds UNIQUEMENT avec un objet JSON valide, sans texte d'accompagnement.
    Les clés du JSON doivent correspondre EXACTEMENT aux éléments de cette liste : {schema_fields}

    Si un champ est absent, vide ou totalement illisible dans l'image, attribue-lui impérativement la valeur null.
    """

    # 2. Gestion d'erreur pour l'appel à l'API Groq
    try:
        # Modèle de vision configuré pour l'extraction de formulaires
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
            max_tokens=1024,
            temperature=0.1  # Réduction de la température à 0.1 pour maximiser le déterminisme
        )
        raw_text = response.choices[0].message.content
    except Exception as e:
        print(f" Erreur lors de l'appel à l'API Groq : {e}")
        return {"error": "Échec de la communication avec l'IA"}

    # 3. Sécurisation et validation DYNAMIQUE avec Pydantic
    try:
        # Nettoyage ultra-robuste contre les hallucinations de texte markdown
        cleaned_text = clean_json_string(raw_text)
        result_dict = json.loads(cleaned_text)
        
        # Sécurité : Si l'IA enveloppe les données dans un nœud racine générique
        if "data" in result_dict and isinstance(result_dict["data"], dict):
            result_dict = result_dict["data"]

        # Affichage de débogage pour la traçabilité en phase de test (Semaine 3)
        print("\n--- [DEBUG] JSON reçu de l'IA ---")
        print(json.dumps(result_dict, indent=2))
        print("--- [DEBUG] Champs attendus ---")
        print(schema_fields)
        print("--------------------------------\n")
        
        # Normalisation des clés pour éviter les crashs de casse (ex: "Nom Complet" vs "nom_complet")
        normalized_result = normalize_dict_keys(result_dict)
        
        # Définition des types pour Pydantic : acceptation de tout type scalaire (Any) ou None (Optional)
        fields_definition = {field: (Optional[Any], None) for field in schema_fields}
        
        # Génération dynamique avec un nom de modèle UNIQUE par requête pour éviter les collisions de cache
        unique_model_name = f"DynamicFormData_{uuid.uuid4().hex[:8]}"
        DynamicFormData = create_model(unique_model_name, **fields_definition)
        
        # Mapping tolérant : on cherche la correspondance normalisée de la clé
        cleaned_dict = {}
        for field in schema_fields:
            normalized_field_key = field.strip().lower().replace(" ", "").replace("_", "").replace("-", "")
            cleaned_dict[field] = normalized_result.get(normalized_field_key, None)
        
        # Validation stricte par Pydantic
        validated_data = DynamicFormData(**cleaned_dict)
        
        # Utilisation de la méthode compatible Pydantic v1 et v2
        return validated_data.dict() if hasattr(validated_data, "dict") else validated_data.model_dump()
        
    except json.JSONDecodeError:
        print(f" Erreur : L'IA n'a pas renvoyé un format JSON valide.")
        print(f"Texte brut reçu : {raw_text}")
        return {"error": "Format JSON invalide renvoyé par l'IA"}
    except Exception as e:
        print(f" Erreur lors de la validation dynamique : {str(e)}")
        return {"error": f"Erreur de validation de structure : {str(e)}"}