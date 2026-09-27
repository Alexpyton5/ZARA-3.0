// Configuração da aba "ZOE" — o app web da zoe embutido na ZARA via <webview>.
// Troque a URL aqui se o endereço do app mudar algum dia.
export const ZOE_APP_URL = 'https://muse.ai';

// Partição persistente do Electron: o login é feito uma vez e a sessão
// da zoe fica salva entre aberturas do app.
export const ZOE_WEBVIEW_PARTITION = 'persist:zoe';
