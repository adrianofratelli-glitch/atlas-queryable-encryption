import React, { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import Bloco from '../components/Bloco'

/**
 * Módulo 04 — o que NÃO funciona.
 *
 * Cada linha executa a operação de verdade e mostra o erro cru do servidor. Nada
 * aqui é texto escrito à mão: o valor da tela está em a mensagem vir do MongoDB.
 */
export default function Fronteiras() {
  const api = useApi()
  const apiModelagem = useApi()
  const [lista, setLista] = useState([])
  const [resultados, setResultados] = useState({})
  const [ocupada, setOcupada] = useState(null)
  const [modelagem, setModelagem] = useState(null)

  useEffect(() => { api.call('/fronteiras/lista').then(d => d && setLista(d.tentativas)) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const tentar = async (chave) => {
    setOcupada(chave)
    const resposta = await api.call(`/fronteiras/tentar/${chave}`)
    setResultados(anterior => ({ ...anterior, [chave]: resposta }))
    setOcupada(null)
  }

  const tentarTudo = async () => {
    for (const item of lista) await tentar(item.chave)
  }

  return (
    <>
      <div className="kicker">módulo 04</div>
      <h1>Fronteiras</h1>
      <p className="tese">
        Uma demo de criptografia que só mostra o que funciona é a demo que perde o segundo
        encontro. Estas operações rodam de verdade contra o cluster, e o que aparece é a
        resposta do servidor — não um texto nosso.
      </p>

      <div className="card">
        <button className="acao acao--secundario" onClick={tentarTudo} disabled={!!ocupada}>
          Rodar todas
        </button>

        <div style={{ marginTop: 16 }}>
          {lista.map(item => {
            const resultado = resultados[item.chave]
            return (
              <div key={item.chave} className="doc">
                <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                  <button className="acao acao--secundario" disabled={ocupada === item.chave}
                    onClick={() => tentar(item.chave)} style={{ minWidth: 96 }}>
                    {ocupada === item.chave ? '…' : 'Tentar'}
                  </button>
                  <div style={{ flex: 1, minWidth: 240 }}>
                    <h3>{item.tentativa}</h3>
                    <code style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{item.comando}</code>
                  </div>
                  {resultado && (
                    <span className={resultado.silenciosa ? 'selo selo--erro'
                      : resultado.funcionou ? 'selo selo--aviso' : 'selo selo--ok'}>
                      {resultado.silenciosa ? 'executou e devolveu resultado errado'
                        : resultado.funcionou ? 'executou — confira o resultado'
                        : 'recusado pelo servidor'}
                    </span>
                  )}
                </div>
                <p className="legenda" style={{ marginTop: 6 }}>{item.razao}</p>
                {resultado?.silenciosa && (
                  <div className="aviso aviso--perigo" style={{ marginTop: 10, display: 'block' }}>
                    <strong>Pior que um erro.</strong> A operação não falhou: ela ordenou por
                    ciphertext e devolveu ordem sem sentido, sem aviso nenhum. Um erro do
                    servidor o time descobre no primeiro teste; uma ordenação errada vai para
                    produção.
                    <div style={{ marginTop: 8 }}>
                      <div className="linha">
                        <span className="linha__rotulo">devolvida</span>
                        <span className="linha__valor">{resultado.resultado.ordem_devolvida.join(' · ')}</span>
                      </div>
                      <div className="linha">
                        <span className="linha__rotulo">ordenada</span>
                        <span className="linha__valor">{resultado.resultado.ordem_real.join(' · ')}</span>
                      </div>
                    </div>
                  </div>
                )}
                {resultado?.erro && <Bloco dados={resultado.erro} rotulo="Ver erro do servidor" erro />}
                {resultado?.resultado && <Bloco dados={resultado.resultado} rotulo="Ver resultado" />}
              </div>
            )
          })}
        </div>
      </div>

      <div className="card">
        <h2>Então como eu faço meu relatório?</h2>
        <p className="tese">
          Campo cifrado é campo de <strong>filtro e leitura</strong>, não de análise. O que se
          agrega é a faixa derivada em claro, calculada pela aplicação no momento da escrita —
          grossa o bastante para não reidentificar, fina o bastante para o relatório servir.
        </p>
        <button className="acao" style={{ marginTop: 12 }} disabled={apiModelagem.loading}
          onClick={() => apiModelagem.call('/fronteiras/modelagem').then(setModelagem)}>
          {apiModelagem.loading ? 'agregando…' : 'Agregar pela faixa derivada'}
        </button>

        {modelagem && (
          <>
            <pre className="codigo" style={{ marginTop: 14 }}>{modelagem.pipeline}</pre>
            <table style={{ marginTop: 12 }}>
              <thead><tr><th>faixa (em claro)</th><th>titulares</th></tr></thead>
              <tbody>
                {modelagem.distribuicao.map(linha => (
                  <tr key={linha._id}><td>{linha._id}</td><td className="num">{linha.titulares}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="legenda" style={{ marginTop: 10 }}>{modelagem.nota}</p>
          </>
        )}
      </div>
    </>
  )
}
