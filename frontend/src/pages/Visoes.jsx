import React, { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import Documento from '../components/Documento'
import Bloco from '../components/Bloco'

/**
 * Módulo 02 — o painel dividido. É a tela que vende.
 *
 * Cada painel tem seu PRÓPRIO useApi: o `loading` do hook é uma flag única para
 * todas as chamadas daquela instância, e um hook compartilhado faria os dois
 * lados piscarem juntos — matando o efeito de "mesma query, dois resultados".
 */
export default function Visoes() {
  const apiComparar = useApi()
  const apiPar = useApi()
  const [uf, setUf] = useState('SP')
  const [dados, setDados] = useState(null)
  const [par, setPar] = useState(null)

  const comparar = () => apiComparar.call(`/visoes/comparar?uf=${encodeURIComponent(uf)}&limite=4`).then(setDados)
  useEffect(() => { comparar() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <div className="kicker">módulo 02</div>
      <h1>Duas visões do mesmo documento</h1>
      <p className="tese">
        A mesma query, no mesmo instante, por dois clientes contra o mesmo cluster.
        À esquerda a aplicação, com auto-encryption. À direita o que enxerga quem tem
        credencial de leitura no banco — o DBA, o time de infraestrutura, o provedor
        de nuvem e quem levar o backup.
      </p>

      <div className="card">
        <div className="campos">
          <div className="campo">
            <label htmlFor="uf">UF (campo em claro)</label>
            <input id="uf" value={uf} maxLength={2} onChange={e => setUf(e.target.value.toUpperCase())} />
          </div>
          <button className="acao" onClick={comparar} disabled={apiComparar.loading}>
            {apiComparar.loading ? 'consultando…' : 'Executar nos dois clientes'}
          </button>
        </div>
        <p className="legenda" style={{ marginTop: 8 }}>
          O filtro usa um campo em claro de propósito: filtrar por campo cifrado é o módulo 03.
        </p>
      </div>

      {dados && (
        <>
          <div className="painel-duplo" style={{ marginTop: 20 }}>
            <div className="painel painel--app">
              <div className="painel__titulo">▚ Aplicação</div>
              <div className="painel__origem">MongoClient + AutoEncryptionOpts</div>
              {dados.aplicacao.map(doc => <Documento key={doc._id} doc={doc} />)}
            </div>
            <div className="painel painel--dba">
              <div className="painel__titulo">▚ DBA · operador · backup</div>
              <div className="painel__origem">MongoClient comum, mesma URI</div>
              {dados.dba.map(doc => <Documento key={doc._id} doc={doc} />)}
            </div>
          </div>
          <p className="legenda" style={{ textAlign: 'center', marginTop: 10 }}>{dados.legenda}</p>
          <Bloco dados={dados.filtro} rotulo="Ver filtro enviado" />
        </>
      )}

      <div className="card">
        <h2>O par plantado: mesmo CPF, ciphertexts diferentes</h2>
        <p className="tese">
          CSFLE usa ciphertext determinístico para permitir igualdade — e por isso vaza
          frequência: com o dump em mãos dá para ver qual valor se repete. Queryable
          Encryption é randomizado e continua consultável.
        </p>
        <button className="acao" style={{ marginTop: 12 }} disabled={apiPar.loading}
          onClick={() => apiPar.call('/visoes/cpf-repetido').then(setPar)}>
          {apiPar.loading ? 'buscando…' : 'Mostrar o par'}
        </button>

        {par && (
          <>
            <div className="painel-duplo" style={{ marginTop: 16 }}>
              <div className="painel painel--app">
                <div className="painel__titulo">▚ Aplicação</div>
                <div className="painel__origem">o mesmo CPF nos dois titulares</div>
                {par.aplicacao.map(doc => <Documento key={doc._id} doc={doc} campos={['_id', 'nome', 'cpf']} />)}
              </div>
              <div className="painel painel--dba">
                <div className="painel__titulo">▚ DBA</div>
                <div className="painel__origem">dois ciphertexts distintos</div>
                {par.dba.map(doc => <Documento key={doc._id} doc={doc} campos={['_id', 'nome', 'cpf']} />)}
              </div>
            </div>
            <div className={par.ciphertexts_distintos ? 'aviso' : 'aviso aviso--perigo'} style={{ marginTop: 12 }}>
              <span>{par.ciphertexts_distintos ? '✓' : '⚠️'}</span>
              <span>{par.afirmacao}</span>
            </div>
          </>
        )}
      </div>
    </>
  )
}
