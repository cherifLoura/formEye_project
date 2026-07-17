FROM python:3.11.9-slim
WORKDIR /app

# 1. Création de l'utilisateur de sécurité au plus tôt
RUN useradd -m -u 1000 myuser

# 2. Installation des dépendances (Optimisation du cache des calques Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 3. Copie du code source en attribuant immédiatement la propriété à myuser
COPY --chown=myuser:myuser . .

# 4. Basculement sur l'utilisateur sécurisé
USER myuser

EXPOSE 8000

# 5. Lancement avec le bon point d'entrée (main:app)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]