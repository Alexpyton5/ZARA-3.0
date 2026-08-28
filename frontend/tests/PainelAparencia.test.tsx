import React from 'react';
import { render, screen } from '@testing-library/react';
import { PainelAparencia } from '../../src/renderer/components/zara/PainelAparencia';

// Mock the aparencia lib
jest.mock('../../src/renderer/lib/aparencia', () => ({
  APARENCIA_PADRAO: { fundo: '#000', destaque: '#fff', segundoFio: '#888', padrao: 'linhas', posicao: 'topo', forca: 'medio', interfaceNova: false },
  APARENCIA_INICIAL: null,
  APARENCIA_INICIAL_VERIFICADA: false,
  FORCAS_PADRAO: [{ id: 'fraco', nome: 'Fraco' }, { id: 'medio', nome: 'Médio' }, { id: 'forte', nome: 'Forte' }],
  PADROES_APARENCIA: [{ id: 'linhas', nome: 'Linhas' }, { id: 'grade', nome: 'Grade' }],
  PELES_APARENCIA: [{ id: 'pele1', nome: 'Pele 1', fundo: '#000', destaque: '#fff', segundoFio: '#888' }],
  POSICOES_PADRAO: [{ id: 'topo', nome: 'Topo' }, { id: 'fundo', nome: 'Fundo' }],
  aplicarAparencia: () => true,
  encontrarPele: () => ({ id: 'pele1' }),
  guardarAparencia: () => true,
  removerAparencia: () => true,
  restaurarAparenciaOriginal: () => true,
}));

describe('PainelAparencia', () => {
  test('renders when aberto prop is true', () => {
    render(<PainelAparencia aberto={true} onClose={() => {}} onInterfaceNovaChange={() => {}} />);
    expect(screen.getByText(/APARÊNCIA/i)).toBeInTheDocument();
  });

  test('does not render when aberto prop is false', () => {
    render(<PainelAparencia aberto={false} onClose={() => {}} onInterfaceNovaChange={() => {}} />);
    expect(screen.queryByText(/APARÊNCIA/i)).not.toBeInTheDocument();
  });

  test('has skin selection buttons', () => {
    render(<PainelAparencia aberto={true} onClose={() => {}} onInterfaceNovaChange={() => {}} />);
    expect(screen.getByRole('button', { name: /Pele 1/i })).toBeInTheDocument();
  });

  test('has color inputs', () => {
    render(<PainelAparencia aberto={true} onClose={() => {}} onInterfaceNovaChange={() => {}} />);
    expect(screen.getByLabelText(/FUNDO/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/DESTAQUE/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/SEGUNDO FIO/i)).toBeInTheDocument();
  });

  test('has pattern selection', () => {
    render(<PainelAparencia aberto={true} onClose={() => {}} onInterfaceNovaChange={() => {}} />);
    expect(screen.getByRole('button', { name: /Linhas/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Grade/i })).toBeInTheDocument();
  });

  test('has position selection', () => {
    render(<PainelAparencia aberto={true} onClose={() => {}} onInterfaceNovaChange={() => {}} />);
    expect(screen.getByRole('button', { name: /Topo/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Fundo/i })).toBeInTheDocument();
  });

  test('has force selection', () => {
    render(<PainelAparencia aberto={true} onClose={() => {}} onInterfaceNovaChange={() => {}} />);
    expect(screen.getByRole('button', { name: /Fraco/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Médio/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Forte/i })).toBeInTheDocument();
  });

  test('has interface nova toggle', () => {
    render(<PainelAparencia aberto={true} onClose={() => {}} onInterfaceNovaChange={() => {}} />);
    expect(screen.getByRole('button', { name: /INTERFACE NOVA/i })).toBeInTheDocument();
  });

  test('has preview section', () => {
    render(<PainelAparencia aberto={true} onClose={() => {}} onInterfaceNovaChange={() => {}} />);
    expect(screen.getByText(/PRÉVIA AO VIVO/i)).toBeInTheDocument();
  });

  test('has footer with buttons', () => {
    render(<PainelAparencia aberto={true} onClose={() => {}} onInterfaceNovaChange={() => {}} />);
    expect(screen.getByRole('button', { name: /VOLTAR AO ORIGINAL/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /GUARDAR/i })).toBeInTheDocument();
  });
});