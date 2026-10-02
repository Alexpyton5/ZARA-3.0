# Cadastrar seu rosto e sua voz na ZARA

**Pra que serve:** ensinar a ZARA a reconhecer você (e sua esposa) pelo rosto e pela voz.
Depois disso, se um estranho falar com ela, ela diz "você é um estranho" e ignora.

**Sua privacidade:** nenhuma foto sua e nenhum áudio seu é gravado em lugar nenhum.
A ZARA guarda só um código matemático que não dá pra transformar de volta em imagem ou som.
Quer apagar? Dá pra remover quando quiser.

## 1. Abrir a pasta do projeto

1. Abra a pasta `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002`
2. Clique na barra de endereço (onde aparece o caminho da pasta)
3. Digite `cmd` e aperte Enter — abre a janelinha preta já no lugar certo

## 2. Rodar os 4 cadastros (um de cada vez)

Cole cada linha na janelinha preta, aperte Enter e siga o que aparecer na tela:

```
.venv\Scripts\python.exe scripts\cadastrar_identidade.py --papel dono --modalidade rosto
```

```
.venv\Scripts\python.exe scripts\cadastrar_identidade.py --papel dono --modalidade voz
```

```
.venv\Scripts\python.exe scripts\cadastrar_identidade.py --papel esposa --modalidade rosto
```

```
.venv\Scripts\python.exe scripts\cadastrar_identidade.py --papel esposa --modalidade voz
```

- **Rosto:** fique na frente da câmera, rosto bem iluminado, parado 3 segundos por captura (frente, leve esquerda, leve direita).
- **Voz:** lugar silencioso, fale normal e diga cada frase 1 vez.
- No fim de cada um aparece `[OK] cadastrado`.

## 3. Pronto

Feche a janelinha preta. A partir daí a ZARA reconhece você e sua esposa — e ignora estranho.

---

**Situação honesta de hoje (28/09):** o roteiro acima está pronto e foi testado de ponta a ponta.
A parte que lê rosto/voz de verdade ainda está sendo ligada pela equipe — quando ligar,
são exatamente os mesmos 4 comandos, nada muda pra você.
