import React, { useEffect, useState } from 'react'
import { useApi } from './hooks/useApi'
import Documento from './components/Documento'
import Bloco from './components/Bloco'

/**
 * A PoV inteira em uma tela. Um argumento só: o servidor executa a busca sem
 * conseguir ler o dado. Tudo que não serve para provar isso ficou de fora.
 */

const EXEMPLO_CPF = '99943750162'

function ErroToast() {
  const [toast, setToast] = useState(null)
  useEffect(() => {
    let timer, ultimaChave = '', ultimoInstante = 0
    const aoErrar = (evento) => {
      const chave = `${evento.detail?.path || ''}:${evento.detail?.message || ''}`
      const agora = Date.now()
      if (chave === ultimaChave && agora - ultimoInstante < 8000) return
      ultimaChave = chave; ultimoInstante = agora
      setToast(evento.detail)
      clearTimeout(timer)
      timer = setTimeout(() => setToast(null), 6000)
    }
    window.addEventListener('api-error', aoErrar)
    return () => { window.removeEventListener('api-error', aoErrar); clearTimeout(timer) }
  }, [])
  if (!toast) return null
  return (
    <div className="aviso aviso--perigo" role="status"
      style={{ position: 'fixed', bottom: 24, right: 24, maxWidth: 420, zIndex: 1000 }}>
      <span>⚠️</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <strong>Erro na chamada à API</strong>
        <div style={{ wordBreak: 'break-word' }}><code>{toast.path}</code> — {toast.message}</div>
      </div>
      <button className="acao acao--secundario" onClick={() => setToast(null)}
        aria-label="Fechar aviso" style={{ padding: '2px 8px' }}>×</button>
    </div>
  )
}

/** Um preflight vermelho no palco tem que aparecer antes de alguém clicar. */
function SeloPreflight() {
  const { call } = useApi()
  const [estado, setEstado] = useState(null)
  useEffect(() => { call('/preflight').then(setEstado) }, [call])
  if (!estado) return <span className="selo">verificando…</span>
  const reprovados = Object.entries(estado.checks || {}).filter(([, c]) => !c.ok)
  if (estado.ready) return <span className="selo selo--ok">✓ pré-voo ok</span>
  return (
    <span className="selo selo--erro" title={reprovados.map(([k, c]) => `${k}: ${c.message}`).join('\n')}>
      pré-voo pendente ({reprovados.length})
    </span>
  )
}

function Painel({ titulo, sub, dados, destaque }) {
  if (!dados) return null
  return (
    <div className={destaque ? 'painel painel--app' : 'painel painel--dba'}>
      <div className="painel__titulo">{titulo}</div>
      <div className="painel__origem">{sub}</div>
      <p className="legenda" style={{ margin: '0 0 12px' }}>
        {dados.encontrados} documento(s) · {dados.ms} ms
      </p>
      {dados.encontrados === 0
        ? <span className="selo selo--ok">zero — o valor em claro não casa com nada</span>
        : dados.documentos.map(doc => <Documento key={doc._id} doc={doc} />)}
    </div>
  )
}

const ALTERNATIVAS = [
  ['TDE · disco cifrado', 'cifra em repouso; quem tem credencial de leitura vê tudo em claro', 'nao'],
  ['CSFLE determinístico', 'permite igualdade porque o mesmo valor vira o mesmo ciphertext — e é isso que vaza frequência no dump', 'meio'],
  ['pgcrypto / cifrar na aplicação', 'protege o valor, mas o banco deixa de conseguir filtrar por ele', 'nao'],
  ['Queryable Encryption', 'ciphertext randomizado E consultável: igualdade e faixa, com a chave fora do servidor', 'sim'],
]

export default function App() {
  const apiBusca = useApi()
  const apiPar = useApi()
  const [cpf, setCpf] = useState(EXEMPLO_CPF)
  const [minimo, setMinimo] = useState(8000)
  const [maximo, setMaximo] = useState(15000)
  const [resultado, setResultado] = useState(null)
  const [par, setPar] = useState(null)

  const buscar = (params) => apiBusca.call(`/demo/buscar?${new URLSearchParams(params)}`).then(setResultado)

  return (
    <div className="app app--simples">
      <header className="topo">
        <div className="topo__marca">
          <svg aria-hidden="true" width="26" height="26" viewBox="0 0 256 549" fill="none">
            <path d="M175.622 61.108C152.612 33.807 132.797 5.315 128.69.239c-.5-.32-1-.239-1-.239s-.5-.081-1 .239C122.583 5.315 102.768 33.807 79.758 61.108 24.914 128.23 0 188.949 0 245.85c0 68.687 31.064 130.1 79.875 171.037l1.872 1.253c1.522 16.09 4.254 51.884 3.551 75.43 0 0 4.596 3.112 9.94 3.928 5.343.816 11.435.816 11.435.816l-1.114-15.274c8.828 1.952 17.9 3.025 27.22 3.025 9.323 0 18.393-1.073 27.22-3.025l-1.114 15.274s6.093 0 11.435-.816c5.343-.816 9.94-3.928 9.94-3.928-.703-23.546 2.029-59.34 3.55-75.43l1.873-1.253C233.936 375.95 265 314.537 265 245.85c0-56.901-24.914-117.62-89.378-184.742z" fill="#00ED64"/>
          </svg>
          <div>
            <strong>Queryable Encryption</strong>
            <span>o servidor executa a busca sem conseguir ler o dado</span>
          </div>
        </div>
        <SeloPreflight />
      </header>

      <main className="conteudo conteudo--simples">
        <p className="tese">
          Os dois painéis abaixo são <strong>dois clientes contra o mesmo cluster, no mesmo
          instante</strong>. À esquerda a sua aplicação, com auto-encryption. À direita quem tem
          credencial de leitura no banco: o DBA, o time de infraestrutura, o provedor de nuvem e
          quem levar o backup.
        </p>

        <div className="card">
          <div className="campos">
            <div className="campo">
              <label>CPF (campo cifrado)</label>
              <input value={cpf} onChange={e => setCpf(e.target.value)} placeholder="99912345678" />
            </div>
            <button className="acao" disabled={apiBusca.loading || !cpf}
              onClick={() => buscar({ cpf })}>
              Buscar por igualdade
            </button>
          </div>

          <div className="campos" style={{ marginTop: 14 }}>
            <div className="campo">
              <label>salário ≥</label>
              <input type="number" value={minimo} onChange={e => setMinimo(+e.target.value)} />
            </div>
            <div className="campo">
              <label>salário ≤</label>
              <input type="number" value={maximo} onChange={e => setMaximo(+e.target.value)} />
            </div>
            <button className="acao" disabled={apiBusca.loading}
              onClick={() => buscar({ salario_min: minimo, salario_max: maximo })}>
              Buscar por faixa
            </button>
            <button className="acao acao--secundario" disabled={apiBusca.loading}
              onClick={() => buscar({ uf: 'SP' })}
              title="Campo em claro: o controle do experimento">
              Buscar por UF (campo em claro)
            </button>
          </div>

          {apiBusca.loading && <p className="legenda" style={{ marginTop: 14 }}>consultando os dois clientes…</p>}

          {resultado && (
            <>
              <div className="aviso" style={{ marginTop: 16 }}>
                <span>ℹ️</span>
                <span><strong>{resultado.tipo}</strong> — {resultado.leitura}</span>
              </div>
              <div className="painel-duplo">
                <Painel titulo="SUA APLICAÇÃO" sub="MongoClient + AutoEncryptionOpts"
                  dados={resultado.aplicacao} destaque />
                <Painel titulo="O DBA · O BACKUP · A NUVEM" sub="MongoClient comum, mesma URI"
                  dados={resultado.dba} />
              </div>
              <Bloco dados={resultado.filtro} rotulo="Ver o filtro que saiu daqui" />
            </>
          )}
        </div>

        <div className="card">
          <h2>Por que isso não é o que você já tem</h2>
          <p className="tese">
            Cifrar não é o difícil — <strong>continuar consultando é</strong>. Todo o resto do
            mercado escolhe um dos dois.
          </p>
          <table style={{ marginTop: 14 }}>
            <tbody>
              {ALTERNATIVAS.map(([nome, texto, veredito]) => (
                <tr key={nome} className={veredito === 'sim' ? 'linha--destaque' : undefined}>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <strong>{nome}</strong>
                  </td>
                  <td>{texto}</td>
                  <td className="num">
                    {veredito === 'sim' ? '✓' : veredito === 'meio' ? '⚠' : '✗'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3 style={{ marginTop: 22 }}>A prova de que é randomizado</h3>
          <p className="tese">
            Dois titulares diferentes com o <strong>mesmo CPF</strong>. Se os ciphertexts fossem
            iguais, quem tem o dump contaria repetições e reidentificaria — é exatamente o que
            CSFLE determinístico entrega.
          </p>
          <button className="acao" disabled={apiPar.loading}
            onClick={() => apiPar.call('/demo/par-repetido').then(setPar)}>
            {apiPar.loading ? 'lendo…' : 'Mostrar o par'}
          </button>

          {par && (
            <>
              <div className="painel-duplo" style={{ marginTop: 14 }}>
                <div className="painel painel--app">
                  <div className="painel__titulo">SUA APLICAÇÃO</div>
                  <div className="painel__origem">o mesmo CPF nos dois titulares</div>
                  {par.aplicacao.map(d => <Documento key={d._id} doc={d} campos={['_id', 'nome', 'cpf']} />)}
                </div>
                <div className="painel painel--dba">
                  <div className="painel__titulo">O DBA</div>
                  <div className="painel__origem">dois ciphertexts distintos</div>
                  {par.dba.map(d => <Documento key={d._id} doc={d} campos={['_id', 'nome', 'cpf']} />)}
                </div>
              </div>
              <div className={par.ciphertexts_distintos ? 'aviso' : 'aviso aviso--perigo'}>
                <span>{par.ciphertexts_distintos ? '✓' : '⚠️'}</span>
                <span>{par.leitura}</span>
              </div>
            </>
          )}
        </div>

        <p className="legenda" style={{ textAlign: 'center', margin: '8px 0 32px' }}>
          Dado sintético. Os CPF têm dígito verificador válido e prefixo <code>999</code>, uma
          faixa não emitida — não pertencem a ninguém.
        </p>
      </main>

      <ErroToast />
    </div>
  )
}
