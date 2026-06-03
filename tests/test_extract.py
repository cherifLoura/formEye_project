from app.extractor import extract_form_data

# Test avec une image fictive — on va en mettre une vraie juste après
result = extract_form_data(
    image_path="images/imgTest.png",
    prompt="Ceci est un exemple portant sur une fiche d'inspection de chantier",
    schema_fields=["nom", "date", "montant", "description", "statut"]
)

print("Bingo... Résultat extrait avec succès!")
print(result)