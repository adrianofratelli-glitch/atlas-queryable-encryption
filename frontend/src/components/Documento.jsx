import React from 'react'
import Cifra from './Cifra'

/**
 * A ORDEM DOS CAMPOS É FIXA e igual nos dois painéis. Se cada lado renderizar na
 * ordem que o BSON devolveu, as linhas desalinham e o efeito de "mesmo documento,
 * duas leituras" — que é a tela inteira do módulo 02 — desaparece.
 */
export const ORDEM = ['_id', 'nome', 'cpf', 'email', 'salario', 'score_credito', 'uf', 'cidade', 'faixa_salarial', 'tenant_id']

/** Marca onde o trecho buscado casou dentro do valor decifrado. */
function Destacado({ texto, trecho, modo }) {
  const t = String(texto)
  const i = modo === 'prefixo' ? (t.startsWith(trecho) ? 0 : -1)
    : modo === 'sufixo' ? (t.endsWith(trecho) ? t.length - trecho.length : -1)
    : t.indexOf(trecho)
  if (i < 0) return <span className="linha__valor">{t}</span>
  return (
    <span className="linha__valor">
      {t.slice(0, i)}<mark className="casou">{t.slice(i, i + trecho.length)}</mark>{t.slice(i + trecho.length)}
    </span>
  )
}

export default function Documento({ doc, campos = ORDEM, destaque }) {
  if (!doc) return null
  return (
    <div className="doc">
      {campos.filter(campo => doc[campo] !== undefined).map(campo => (
        <div className="linha" key={campo}>
          <span className="linha__rotulo">{campo}</span>
          {destaque && destaque.campo === campo && typeof doc[campo] === 'string'
            ? <Destacado texto={doc[campo]} trecho={destaque.trecho} modo={destaque.modo} />
            : <Cifra valor={doc[campo]} />}
        </div>
      ))}
    </div>
  )
}
