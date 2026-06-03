from pydantic import BaseModel
from typing import Optional

# Un schéma exemple : une fiche d'inspection simple
class FormData(BaseModel):
    nom: Optional[str] = None
    date: Optional[str] = None
    montant: Optional[str] = None
    description: Optional[str] = None
    statut: Optional[str] = None