## Referência — regex de DDL destrutivo

Usada no Passo 6.1 do ship. Case-insensitive. Conservadora — falso positivo > falso negativo.

```
\bDROP\s+(TABLE|COLUMN|CONSTRAINT|INDEX|SCHEMA|VIEW|FUNCTION|TRIGGER|POLICY|TYPE|DATABASE|ROLE)\b
\bTRUNCATE\s+(TABLE\s+)?\w+
\bDELETE\s+FROM\s+\w+(?![\s\S]*\bWHERE\b)
\bALTER\s+(TABLE|COLUMN)\s+.*\bDROP\b
\bALTER\s+(TABLE|COLUMN)\s+.*\bALTER\s+COLUMN\s+.*\bTYPE\b
\bGRANT\s+.*\bALL\b
\bREVOKE\b
```

`project.migrations.destructive_regex_extra[]` adiciona padrões custom. Qualquer match → DESTRUCTIVE → exigir confirmação.

---
