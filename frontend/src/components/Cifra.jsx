import React from 'react'

/**
 * Renderiza um valor vindo do backend respeitando a regra da PoV: nada na tela
 * sem procedência. Ciphertext aparece rotulado, em âmbar, com o tamanho real em
 * bytes ao lado — é ele que explica o overhead de storage do módulo 06.
 */
export default function Cifra({ valor }) {
  if (valor === null || valor === undefined) return <span className="legenda">—</span>

  if (typeof valor === 'object' && valor.__cifrado__ !== undefined) {
    if (!valor.__cifrado__) {
      return <span className="linha__valor">Binary(subtype {valor.subtype}) · {valor.bytes} B</span>
    }
    // A amostra vem do PAYLOAD, nunca do começo do blob: os 17 primeiros bytes
    // são tipo + UUID da DEK e são idênticos em todo valor do mesmo campo.
    // Exibi-los faria dois valores distintos parecerem o mesmo ciphertext.
    return (
      <span>
        <span className="cifra">{valor.hex}{valor.fim ? `…${valor.fim}` : '…'}</span>
        <span className="cifra__bytes">
          {valor.bytes} B · subtype 6{valor.chave ? ` · DEK ${valor.chave.slice(0, 8)}` : ''}
        </span>
      </span>
    )
  }

  if (typeof valor === 'object') return <span className="linha__valor">{JSON.stringify(valor)}</span>
  return <span className="linha__valor">{String(valor)}</span>
}
