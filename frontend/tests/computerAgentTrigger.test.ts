import assert from 'node:assert/strict';
import test from 'node:test';

import {
  COMPUTER_TRIGGER_PREFIX,
  extractComputerGoal,
  extractZoeComputerGoal,
  isComputerAgentTrigger,
} from '../src/renderer/lib/computerAgentTrigger';

test('detecta o gatilho e extrai o goal', () => {
  assert.equal(
    extractComputerGoal('use o computador para abrir o bloco de notas'),
    'abrir o bloco de notas',
  );
  assert.equal(isComputerAgentTrigger('use o computador para abrir o bloco de notas'), true);
});

test('ignora maiúsculas/minúsculas e espaços no início', () => {
  assert.equal(extractComputerGoal('  Use O Computador Para   pesquisar voos  '), 'pesquisar voos');
});

test('retorna null para mensagem de chat comum', () => {
  assert.equal(extractComputerGoal('qual a previsão do tempo?'), null);
  assert.equal(isComputerAgentTrigger('qual a previsão do tempo?'), false);
});

test('gatilho sem goal retorna string vazia (o chat pede para descrever)', () => {
  assert.equal(extractComputerGoal('use o computador para'), '');
  assert.equal(isComputerAgentTrigger('use o computador para'), true);
});

test('não dispara no meio da frase nem com prefixo parecido', () => {
  assert.equal(extractComputerGoal('quero que use o computador para isso'), null);
  assert.equal(extractComputerGoal('use o computadores para isso'), null);
});

test('o prefixo exportado é o que o botão "usar PC" insere', () => {
  assert.equal(COMPUTER_TRIGGER_PREFIX, 'use o computador para');
});

test('fala natural na aba Zoe aciona o PC sem confundir conversa comum', () => {
  assert.equal(extractZoeComputerGoal('Zoe, abre o bloco de notas e escreve "oi"'), 'abre o bloco de notas e escreve "oi"');
  assert.equal(extractZoeComputerGoal('Zoe, feche o bloco de notas'), 'feche o bloco de notas');
  assert.equal(extractZoeComputerGoal('use o computador para clique em Salvar'), 'clique em Salvar');
  assert.equal(extractZoeComputerGoal('me conte como está o projeto'), null);
});
