 #type:ignore
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
import time
from typing import Dict, Tuple

# Header HTTP où l'utilisateur doit passer sa clé (ex: X-API-Key: ma_cle_premium)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

# 1. Base de données fictive des clés valides (À remplacer par ta DB à l'oral)
USER_KEYS = {
    "cle_standard_demo": {"tier": "standard", "owner": "User A"},
    "cle_premium_demo": {"tier": "premium", "owner": "User B"}
}

# 2. Définition des quotas par catégorie (Requêtes/Sec, Requêtes/Jour)
QUOTAS = {
    "standard": {"per_second": 2, "per_day": 100},
    "premium": {"per_second": 10, "per_day": 5000}
}

# 3. Stockage en mémoire des historiques de requêtes
# Structure: { cle_api: ([timestamps_seconde], [timestamps_jour]) }
USAGE_HISTORY: Dict[str, Tuple[list, list]] = {}

def verify_rate_limit(api_key: str = Security(api_key_header)) -> dict:
    """
    Dépendance FastAPI qui valide la clé d'API et applique les restrictions
    de requêtes par seconde et par jour selon le Tier de l'utilisateur.
    """
    # Vérification de l'existence de la clé
    if api_key not in USER_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clé d'API invalide ou manquante."
        )
        
    user_info = USER_KEYS[api_key]
    tier = user_info["tier"]
    limits = QUOTAS[tier]
    
    current_time = time.time()
    
    # Initialisation de l'historique pour cette clé si première utilisation
    if api_key not in USAGE_HISTORY:
        USAGE_HISTORY[api_key] = ([], [])
        
    sec_history, day_history = USAGE_HISTORY[api_key]
    
    # Nettoyage des anciens enregistrements (Fenêtres glissantes)
    sec_history = [t for t in sec_history if current_time - t < 1.0]
    day_history = [t for t in day_history if current_time - t < 86400.0]
    
    # Mise à jour de la mémoire globale
    USAGE_HISTORY[api_key] = (sec_history, day_history)
    
    # --- Vérification du quota PAR SECONDE ---
    if len(sec_history) >= limits["per_second"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Limite par seconde dépassée pour le tier {tier}. Maximum: {limits['per_second']}/s"
        )
        
    # --- Vérification du quota PAR JOUR ---
    if len(day_history) >= limits["per_day"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Quota journalier épuisé pour le tier {tier}. Maximum: {limits['per_day']}/jour"
        )
        
    # Si tout est OK, on enregistre la requête actuelle
    sec_history.append(current_time)
    day_history.append(current_time)
    
    return {"owner": user_info["owner"], "tier": tier}