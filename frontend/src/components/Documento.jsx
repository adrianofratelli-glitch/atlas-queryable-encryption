import React from 'react'
import Cifra from './Cifra'

/**
 * A ORDEM DOS CAMPOS É FIXA e igual nos dois painéis. Se cada lado renderizar na
 * ordem que o BSON devolveu, as linhas desalinham e o efeito de "mesmo documento,
 * duas leituras" — que é a tela inteira do módulo 02 — desaparece.
 */
export const ORDEM = ['_id', 'nome', 'cpf', 'email', 'salario', 'score_credito', 'uf', 'cidade', 'faixa_salarial', 'tenant_id']

export default function Documento({ doc, campos = ORDEM }) {
  if (!doc) return null
  return (
    <div className="doc">
      {campos.filter(campo => doc[campo] !== undefined).map(campo => (
        <div className="linha" key={campo}>
          <span className="linha__rotulo">{campo}</span>
          <Cifra valor={doc[campo]} />
        </div>
      ))}
    </div>
  )
}
