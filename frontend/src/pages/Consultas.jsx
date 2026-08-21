import React, { useState } from 'react'
import { useApi } from '../hooks/useApi'
import Documento from '../components/Documento'
import Bloco from '../components/Bloco'

/** Módulo 03 — igualdade e faixa sobre ciphertext, com a contraprova. */
export default function Consultas() {
  const apiIgualdade = useApi()
  const apiFaixa = useApi()
  const apiExplain = useApi()

  const [cpf, setCpf] = useState('')
  const [igualdade, setIgualdade] = useState(null)
  const [minimo, setMinimo] = useState(8000)
  const [maximo, setMaximo] = useState(15000)
  const [faixa, setFaixa] = useState(null)
  const [explain, setExplain] = useState(null)

  return (
    <>
      <div className="kicker">módulo 03</div>
      <h1>Consulta sobre dado cifrado</h1>
      <p className="tese">
        O driver cifra o valor da busca com a mesma DEK e envia o ciphertext. O servidor
        casa contra estruturas de metadados cifradas que ele consegue usar sem conseguir
        interpretar. Nenhum plaintext atravessa a rede, e nenhum existe no servidor.
      </p>

      <div className="card">
        <h2>Igualdade</h2>
        <div className="campos">
          <div className="campo">
            <label htmlFor="cpf">CPF (copie um do módulo 02)</label>
            <input id="cpf" value={cpf} placeholder="99912345678" maxLength={14}
              onChange={e => setCpf(e.target.value)} style={{ width: 200 }} />
          </div>
          <button className="acao" disabled={apiIgualdade.loading || cpf.replace(/\D/g, '').length !== 11}
            onClick={() => apiIgualdade.call(`/consultas/igualdade?cpf=${encodeURIComponent(cpf)}`).then(setIgualdade)}>
            {apiIgualdade.loading ? 'consultando…' : 'Buscar'}
          </button>
        </div>

        {igualdade && (
          <div className="painel-duplo" style={{ marginTop: 16 }}>
            <div className="painel painel--app">
              <div className="painel__titulo">▚ Cliente cifrado</div>
              <div className="painel__origem">
                {igualdade.aplicacao.encontrados} documento(s) · {igualdade.aplicacao.ms} ms
              </div>
              {igualdade.aplicacao.documentos.map(doc => <Documento key={doc._id} doc={doc} />)}
            </div>
            <div className="painel painel--dba">
              <div className="painel__titulo">▚ Cliente claro — mesmo filtro</div>
              <div className="painel__origem">
                {igualdade.dba.encontrados} documento(s) · {igualdade.dba.ms} ms
              </div>
              <div className={igualdade.dba.encontrados === 0 ? 'selo selo--ok' : 'selo selo--erro'}>
                {igualdade.dba.encontrados === 0 ? '✓ zero — como esperado' : 'inesperado'}
              </div>
              <p className="legenda" style={{ marginTop: 10 }}>{igualdade.dba.nota}</p>
            </div>
          </div>
        )}
      </div>

      <div className="card">
        <h2>Faixa</h2>
        <p className="tese">O que ninguém espera que funcione. GA a partir do MongoDB 8.0.</p>
        <div className="campos" style={{ marginTop: 12 }}>
          <div className="campo">
            <label htmlFor="min">salário ≥</label>
            <input id="min" type="number" value={minimo} onChange={e => setMinimo(+e.target.value)} style={{ width: 120 }} />
          </div>
          <div className="campo">
            <label htmlFor="max">salário ≤</label>
            <input id="max" type="number" value={maximo} onChange={e => setMaximo(+e.target.value)} style={{ width: 120 }} />
          </div>
          <button className="acao" disabled={apiFaixa.loading || minimo >= maximo}
            onClick={() => apiFaixa.call(`/consultas/faixa?campo=salario&minimo=${minimo}&maximo=${maximo}`).then(setFaixa)}>
            {apiFaixa.loading ? 'consultando…' : 'Filtrar faixa'}
          </button>
        </div>

        {faixa && (
          <>
            <div className="grade grade--3" style={{ marginTop: 16 }}>
              <div className="metrica">
                <div className="metrica__valor" style={{ color: 'var(--accent)' }}>{faixa.aplicacao.encontrados}</div>
                <div className="metrica__rotulo">cliente cifrado</div>
              </div>
              <div className="metrica">
                <div className="metrica__valor">{faixa.aplicacao.ms} ms</div>
                <div className="metrica__rotulo">latência</div>
              </div>
              <div className="metrica">
                <div className="metrica__valor" style={{ color: 'var(--cifrado)' }}>{faixa.dba.encontrados}</div>
                <div className="metrica__rotulo">cliente claro (esperado 0)</div>
              </div>
            </div>
            <div style={{ marginTop: 16 }}>
              {faixa.aplicacao.documentos.map(doc => <Documento key={doc._id} doc={doc} />)}
            </div>
            <div className="aviso"><span>ℹ️</span><span>{faixa.nota}</span></div>
          </>
        )}
      </div>

      <div className="card">
        <h2>O servidor executou sem plaintext</h2>
        <p className="tese">
          O explain aqui serve para mostrar <em>que</em> o servidor executou contra
          estruturas cifradas — não para otimizar. Não há plano legível dentro das
          <code> enxcol_.*</code>, e não há o que ajustar nelas.
        </p>
        <button className="acao acao--secundario" style={{ marginTop: 12 }} disabled={apiExplain.loading}
          onClick={() => apiExplain.call('/consultas/explain?campo=salario').then(setExplain)}>
          {apiExplain.loading ? 'lendo…' : 'Ver explain'}
        </button>
        {explain && (
          <>
            <p className="legenda" style={{ marginTop: 12 }}>
              contention configurado: <strong>{explain.contention_configurado}</strong> — {explain.nota_contention}
            </p>
            <Bloco dados={explain.winningPlan} rotulo="Ver winningPlan" />
          </>
        )}
      </div>
    </>
  )
}
