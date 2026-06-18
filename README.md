graph TD
    %% Définition des composants
    Client[Postman / Frontend Client]
    
    subgraph FastAPI_Application [Application FastAPI]
        Router[Routeur: app/main.py <br><i>Route /extract</i>]
        Storage[Gestionnaire Stockage <br><i>Dossier local /images</i>]
        Extractor[Extracteur: app/extractor.py <br><i>Logique Métier</i>]
    end
    
    GroqAPI[API Groq <br><i>Llama-4 Vision</i>]
    Pydantic[Usine Pydantic <br><i>create_model() Dynamique</i>]
    
    %% Interactions et flux
    Client -->|1. POST multipart/form-data <br> image, prompt, fields| Router
    Router -->|2. Validation extension <br>& Génération UUID| Router
    Router -->|3. Sauvegarde binaire| Storage
    Router -->|4. Analyse document| Extractor
    Extractor -->|5. Payload Base64 & Meta-Prompt| GroqAPI
    GroqAPI -->|6. JSON Brut| Extractor
    Extractor -->|7. Validation & Alignement| Pydantic
    Pydantic -->|8. Données Typées & Nettoyées| Extractor
    Extractor -->|9. Dictionnaire Validé| Router
    Router -->|10. HTTP 200 OK Response| Client

    %% Styles visuels
    style Client fill:#2563EB,stroke:#1E40AF,color:#FFF
    style FastAPI_Application fill:#F8FAFC,stroke:#334155,stroke-width:2px
    style Router fill:#05966 9,stroke:#047857,color:#FFF
    style GroqAPI fill:#7C3AED,stroke:#6D28D9,color:#FFF
    style Pydantic fill:#EA580C,stroke:#C2410C,color:#FFF

    #-- NB: Ce fichier est réalisé sous forme de diagramme avec Mermaid pour faciliter la visualisation et une meilleure compréhension