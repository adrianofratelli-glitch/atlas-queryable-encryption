import React, { useState } from 'react'
import { useApi } from '../hooks/useApi'
import Bloco from '../components/Bloco'

/** Módulo 06 — o número que decide se o projeto acontece. */
const bytes = (n) => {
  if (n == null) return '—'
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)} GB`
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)} kB`
  return `${n} B`
}

/** A latência da rede até o cluster entra em todo número desta tela. Sem ela ao
 *  lado, o custo do RTT vira "custo da criptografia" na cabeça de quem assiste. */
function Base({ base }) {
  if (!base) return null
  return (
    <>
      <p className="legenda" style={{ marginTop: 10 }}>
        Linha de base da rede ({base.n} pings): p50 {base.p50} ms · p95 {base.p95} ms.
        Todo número acima já a inclui.
      </p>
      {base.suspeito && <div className="aviso aviso--perigo"><span>⚠️</span><span>{base.nota}</span></div>}
    </>
  )
}

export default function Custo() {
  const apiStorage = useApi()
  const apiEscrita = useApi()
  const apiLeitura = useApi()
  const [storage, setStorage] = useState(null)
  const [escrita, setEscrita] = useState(null)
  const [leitura, setLeitura] = useState(null)

  return (
    <>
      <div className="kicker">módulo 06</div>
      <h1>O preço da privacidade</h1>
      <p className="tese">
        Duas coleções com o mesmo dataset, uma cifrada e uma em claro. Todo número desta
        tela precisa carregar o tier do cluster e o tamanho da amostra ao lado — um número
        sem eles não significa nada.
      </p>
      <div className="aviso" style={{ marginTop: 14 }}>
        <span>ℹ️</span>
        <span>
          Enquanto o cluster não roda, o estado correto desta tela é <strong>A MEDIR</strong>.
          Preencher com estimativa e apresentar como medição é o único jeito de perder a reunião
          de forma irrecuperável.
        </span>
      </div>

      <div className="card">
        <h2>Storage</h2>
        <p className="tese">
          As coleções de metadados <code>enxcol_.esc</code> e <code>enxcol_.ecoc</code> contam.
          Ignorá-las é subestimar e virar surpresa em produção.
        </p>
        <button className="acao" style={{ marginTop: 12 }} disabled={apiStorage.loading}
          onClick={() => apiStorage.call('/custo/storage').then(setStorage)}>
          {apiStorage.loading ? 'lendo collStats…' : 'Medir storage'}
        </button>

        {!storage && <div style={{ marginTop: 14 }}><span className="selo selo--medir">A MEDIR</span></div>}

        {storage && (
          <>
            <table style={{ marginTop: 14 }}>
              <thead><tr><th>coleção</th><th>documentos</th><th>armazenado</th><th>índices</th></tr></thead>
              <tbody>
                {[storage.cifrada, storage.metadados.esc, storage.metadados.ecoc, storage.clara].map(item => (
                  <tr key={item.colecao}>
                    <td>{item.colecao}</td>
                    <td className="num">{item.documentos ?? '—'}</td>
                    <td className="num">{bytes(item.armazenado_bytes)}</td>
                    <td className="num">{bytes(item.indices_bytes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="grade grade--3" style={{ marginTop: 14 }}>
              <div className="metrica">
                <div className="metrica__valor" style={{ color: 'var(--cifrado)' }}>{bytes(storage.total_cifrado_bytes)}</div>
                <div className="metrica__rotulo">cifrado + metadados</div>
              </div>
              <div className="metrica">
                <div className="metrica__valor">{bytes(storage.total_claro_bytes)}</div>
                <div className="metrica__rotulo">em claro</div>
              </div>
              <div className="metrica">
                <div className="metrica__valor" style={{ color: 'var(--accent)' }}>{storage.fator ? `${storage.fator}×` : '—'}</div>
                <div className="metrica__rotulo">fator</div>
              </div>
            </div>
            <p className="legenda" style={{ marginTop: 10 }}>
              {storage.nota_tier} Amostra: {storage.cifrada.documentos} documentos, {storage.campos_cifrados} campos cifrados.
            </p>
            {storage.aviso && <div className="aviso aviso--perigo"><span>⚠️</span><span>{storage.aviso}</span></div>}
          </>
        )}
      </div>

      <div className="card">
        <h2>Latência de escrita</h2>
        <button className="acao" disabled={apiEscrita.loading}
          onClick={() => apiEscrita.call('/custo/escrita', { timeoutMs: 600_000 }).then(setEscrita)}>
          {apiEscrita.loading ? 'medindo…' : 'Medir escrita'}
        </button>
        {!escrita && <div style={{ marginTop: 14 }}><span className="selo selo--medir">A MEDIR</span></div>}
        {escrita && (
          <>
            <table style={{ marginTop: 14 }}>
              <thead><tr><th>coleção</th><th>n</th><th>p50</th><th>p95</th><th>média</th></tr></thead>
              <tbody>
                <tr>
                  <td>cifrada</td><td className="num">{escrita.cifrada_ms.n}</td>
                  <td className="num">{escrita.cifrada_ms.p50} ms</td>
                  <td className="num">{escrita.cifrada_ms.p95} ms</td>
                  <td className="num">{escrita.cifrada_ms.media} ms</td>
                </tr>
                <tr>
                  <td>em claro</td><td className="num">{escrita.clara_ms.n}</td>
                  <td className="num">{escrita.clara_ms.p50} ms</td>
                  <td className="num">{escrita.clara_ms.p95} ms</td>
                  <td className="num">{escrita.clara_ms.media} ms</td>
                </tr>
              </tbody>
            </table>
            <Base base={escrita.linha_de_base_ms} />
            <div className="aviso"><span>ℹ️</span><span>{escrita.onde_esta_o_custo}</span></div>
            <p className="legenda" style={{ marginTop: 10 }}>
              Primeira operação (paga a abertura da DEK contra o KMS, que é rede):
              cifrada {escrita.primeira_operacao_ms?.cifrada} ms · clara {escrita.primeira_operacao_ms?.clara} ms.
              Ela não é custo por operação.
            </p>
            <p className="legenda">{escrita.nota_tier}</p>
          </>
        )}
      </div>

      <div className="card">
        <h2>Latência de leitura</h2>
        <button className="acao" disabled={apiLeitura.loading}
          onClick={() => apiLeitura.call('/custo/leitura', { timeoutMs: 600_000 }).then(setLeitura)}>
          {apiLeitura.loading ? 'medindo…' : 'Medir leitura'}
        </button>
        {!leitura && <div style={{ marginTop: 14 }}><span className="selo selo--medir">A MEDIR</span></div>}
        {leitura && (
          <>
            <table style={{ marginTop: 14 }}>
              <thead><tr><th>cenário</th><th>n</th><th>p50</th><th>p95</th></tr></thead>
              <tbody>
                {Object.entries(leitura.resultados).map(([nome, valores]) => (
                  <tr key={nome}>
                    <td>{nome.replace(/_/g, ' ')}</td>
                    <td className="num">{valores.n}</td>
                    <td className="num">{valores.p50} ms</td>
                    <td className="num">{valores.p95} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Base base={leitura.linha_de_base_ms} />
            <p className="legenda" style={{ marginTop: 10 }}>
              {leitura.nota} Aquecimento: {leitura.aquecimento} leituras por cenário. {leitura.nota_tier}
            </p>
            <Bloco dados={leitura.resultados} rotulo="Ver resultados brutos" />
          </>
        )}
      </div>
    </>
  )
}
