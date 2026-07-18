# Présentations Vibe

Le dossier contient :

- le deck HTML/CSS interactif de 5 slides ;
- le deck PowerPoint anglais de 7 slides, généré à partir de `generate-pptx.cjs`.

## Lancer

Depuis la racine du dépôt :

```bash
uv run python -m http.server 8080 --directory presentation
```

Puis ouvrir <http://localhost:8080>.

## Générer le PowerPoint

Installer la version utilisée pour générer le deck puis lancer :

```bash
npm install --no-save pptxgenjs@4.0.1
node presentation/generate-pptx.cjs
```

Le fichier est créé dans `presentation/Vibe_Presentation_EN.pptx`.

## Contrôles

- `←` / `→`, `Page Up` / `Page Down` ou `Espace` : naviguer ;
- `F` : plein écran ;
- `N` : afficher ou masquer les notes orateur ;
- `Home` / `End` : première ou dernière slide ;
- glisser horizontalement sur écran tactile.
