# Redirecionamento do endereço antigo da Ouvidoria

O manual antigo da Ouvidoria vive no projeto `manual-ouvidoria-hsm` da Vercel
(`https://manual-ouvidoria-hsm.vercel.app`), que é o endereço do QR da
apresentação e dos links já espalhados. Quando a seção Ouvidoria do site novo
estiver escrita, esse projeto deixa de servir a página e passa a redirecionar,
em definitivo, para `/ouvidoria/` do site novo. O `vercel.json` ao lado é esse
projeto inteiro.

## Quando publicar

**Só depois que `/ouvidoria/` existir publicada no site novo** (a fatia da
Ouvidoria, issue #738). Publicar antes disso troca um manual que funciona por um
endereço que cai em página não encontrada.

## Como publicar

```bash
D=$(mktemp -d)
cp docs/manual/redirecionamento/vercel.json "$D"/
cd "$D" && npx vercel@latest link --yes --project manual-ouvidoria-hsm
npx vercel@latest deploy --prod --yes
```

Depois, abrir `https://manual-ouvidoria-hsm.vercel.app` e conferir que a página
para em `https://manual.hospitalsaomatheus.cloud/ouvidoria/`.
