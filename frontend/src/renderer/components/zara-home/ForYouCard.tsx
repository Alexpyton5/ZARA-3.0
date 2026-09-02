

/**
 * "Para você" — o site de referência usa dados fake fixos (João/WhatsApp,
 * reunião, tarefas...). A ZARA não tem hoje uma fonte real para isso
 * (nenhum canal IPC de "itens sugeridos"). Documentado como
 * NOT_CONNECTED_YET em vez de inventar um endpoint novo, conforme a regra
 * da missão de não criar API grande para dado que não existe.
 */
export function ForYouCard() {
  return (
    <section className="zh-section zh-glass-panel" aria-label="Para você">
      <h2>Para você</h2>
      <p className="zh-not-connected">
        NOT_CONNECTED_YET — nenhuma fonte real de sugestões (mensagens, agenda, tarefas)
        exposta pelo backend ainda.
      </p>
    </section>
  );
}
