# Loja Python Escalável - Urban MP

Versão refeita com o estilo novo da Urban MP.

## O que já está pronto
- visual streetwear premium em preto, branco e verde
- tema escuro e claro no topo
- catálogo com card novo
- valor cheio + valor com desconto opcional
- balão de desconto no card e na página do produto
- botão flutuante de WhatsApp no canto inferior esquerdo
- número do suporte puxado da aba admin (`WhatsApp da loja / suporte`)
- pronto para GitHub e Railway

## Rodar local
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

## Deploy Railway
Start command:
```bash
gunicorn wsgi:app
```


## Atualização recente
- seleção de tamanho na página do produto
- botão Finalizar compra agora envia para o carrinho primeiro
- carrinho com miniatura do produto
- pedido salva o tamanho escolhido


## Abertura antes do login
- a rota inicial `/` agora mostra uma abertura com vídeo
- ao terminar o vídeo, o sistema envia automaticamente para o login
- existe botão para pular a abertura


## Ícone do site
- favicon configurado com o ícone verde e branco
- ícone aplicado também na abertura e no topo do site


## Desconto por quantidade
- desconto automático configurável no admin
- padrão: 10% a partir de 3 peças do mesmo produto
- carrinho mostra economia total


## Seleção de cor
- agora as cores dos utensílios podem ser clicadas na página do produto
- a cor escolhida vai para o carrinho e para o pedido
- a miniatura do carrinho acompanha a cor selecionada


## Lupa na imagem do produto
- ao passar o mouse na imagem principal, aparece efeito de lupa
- a prévia ampliada aparece ao lado na página de detalhes
- em celular a lupa fica desativada automaticamente
