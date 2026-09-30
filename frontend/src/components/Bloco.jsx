import React, { useId, useState } from 'react'

/** Bloco recolhível com a resposta crua do servidor. */
export default function Bloco({ dados, rotulo = 'Ver resposta do servidor', erro = false }) {
  const [aberto, setAberto] = useState(false)
  const id = useId()
  if (dados === null || dados === undefined) return null
  return (
    <div style={{ marginTop: 10 }}>
      <button className="acao acao--secundario" aria-expanded={aberto} aria-controls={id}
        onClick={() => setAberto(v => !v)} style={{ fontSize: 12, padding: '5px 11px' }}>
        {aberto ? '▼' : '▶'} {rotulo}
      </button>
      {aberto && (
        <pre id={id} className={erro ? 'codigo codigo--erro' : 'codigo'} style={{ marginTop: 8 }}>
          {typeof dados === 'string' ? dados : JSON.stringify(dados, null, 2)}
        </pre>
      )}
    </div>
  )
}
