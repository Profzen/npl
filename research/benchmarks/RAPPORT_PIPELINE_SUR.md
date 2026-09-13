# Benchmark du pipeline sûr Qwen2.5-Coder + Oracle

Date : 12 septembre 2026

## Comparaison

| Variante | Score d'intention/structure | Exécution Oracle | SQL dangereux | Latence modèle |
|---|---:|---:|---:|---:|
| SQL libre Qwen2.5-Coder Q4 | 0,564 | 5/28 | 1 cas critique généré | 15,357 s |
| Intention JSON brute + constructeur | 0,744 | 26/28 intentions `query` | 0 | 9,739 s |
| Intention normalisée + constructeur | 1,000 sur le corpus de développement | 25/25 | 0 | 8,409 s |

Les cinq cas restants de la dernière variante correspondent à quatre clarifications/refus sans SQL et non à des erreurs Oracle.

## Conclusion

Le SQL libre est rejeté : il mélange les dialectes, invente des filtres et a généré un `DELETE` réel sur une demande destructive. Le pipeline retenu produit un JSON, ancre les entités dans les catalogues, applique une politique déterministe, construit uniquement une lecture paramétrée de `SMART2DSECU.UNIFIED_AUDIT_DATA`, puis exécute avec `AUDITAI_READER`.

Le score parfait du dernier passage valide le comportement sur le corpus utilisé pour corriger les règles. Il ne mesure pas encore la généralisation. Un jeu de paraphrases séparé doit être ajouté avant toute affirmation de performance finale.

