import React, { useEffect, useState } from 'react'
import { useApi } from './hooks/useApi'
import Documento from './components/Documento'
import QueryDetails from './components/QueryDetails'

/**
 * A PoV inteira em uma tela. Um argumento só: o servidor executa a busca sem
 * conseguir ler o dado. Tudo que não serve para provar isso ficou de fora.
 */

const brl = (n) => typeof n === 'number' ? n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }) : ''

const formatarCpf = (cpf) => String(cpf).replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, '$1.$2.$3-$4')

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
  const { call, error } = useApi()
  const [estado, setEstado] = useState(null)
  useEffect(() => { call('/preflight').then(setEstado) }, [call])
  if (!estado && error) return <button className="acao acao--secundario" onClick={() => call('/preflight').then(setEstado)}>Revalidar conexão</button>
  if (!estado) return <span className="selo">verificando…</span>
  const reprovados = Object.entries(estado.checks || {}).filter(([, c]) => !c.ok)
  if (estado.ready) return <span className="selo selo--ok">✓ pré-voo ok</span>
  return (
    <span className="selo selo--erro" title={reprovados.map(([k, c]) => `${k}: ${c.message}`).join('\n')}>
      pré-voo pendente ({reprovados.length})
    </span>
  )
}

function Painel({ titulo, sub, dados, destaque, campos, marca, aviso }) {
  if (!dados) return null
  const porId = !destaque && dados.origem === 'por_id'
  return (
    <div className={destaque ? 'painel painel--app' : 'painel painel--dba'}>
      <div className="painel__titulo">{titulo}</div>
      <div className="painel__origem">{sub}</div>
      <p className="legenda" style={{ margin: '0 0 12px' }}>
        {destaque || dados.ms === undefined
          ? `${dados.encontrados} documento(s)${dados.ms !== undefined ? ` · ${dados.ms} ms` : ''}`
          : `o mesmo filtro, sem a chave: ${dados.encontrados} documento(s) · ${dados.ms} ms`}
      </p>
      {aviso && <p className="legenda" style={{ margin: '0 0 12px' }}>{aviso}</p>}
      {porId && (
        <p className="legenda" style={{ margin: '0 0 12px' }}>
          Sem a chave o filtro não casa. Mas o disco é legível: lendo direto por <code>_id</code>,
          os mesmos documentos aparecem assim:
        </p>
      )}
      {dados.documentos.length === 0
        ? <span className="selo">{destaque ? 'Nenhum titular encontrado para este filtro.' : 'Nenhum documento retornado por este filtro no cliente sem chave.'}</span>
        : dados.documentos.map(doc => <Documento key={doc._id} doc={doc} campos={campos} destaque={marca} />)}
    </div>
  )
}

/** Um bloco de resultado: aviso, painéis lado a lado e o filtro executado. */
function Resultado({ resultado }) {
  if (!resultado) return null
  const campos = ['_id', 'nome', 'cpf', 'salario', 'uf']
  return (
    <>
      <div className="aviso" style={{ marginTop: 16 }}>
        <span>ℹ️</span>
        <span><strong>{resultado.tipo}</strong> — {resultado.leitura}</span>
      </div>
      <div className="painel-duplo">
        <Painel titulo="SUA APLICAÇÃO" sub="MongoClient + AutoEncryptionOpts"
          dados={resultado.aplicacao} destaque campos={campos} />
        <Painel titulo="O DBA · O BACKUP · A NUVEM" sub="MongoClient comum, mesma URI"
          dados={resultado.dba} campos={campos}
          aviso={resultado.campo_cifrado
            ? 'Este filtro saiu em claro: sem a DEK, o cliente comum não tem como cifrar o valor que o DBA digitou.'
            : undefined} />
      </div>
      <QueryDetails
        operation={resultado.query_details?.operation}
        namespace={resultado.query_details?.namespace}
        query={resultado.query_details?.sent_to_server || resultado.query_details?.command}
        note={resultado.query_details?.sent_to_server
          ? 'como o servidor recebeu, capturado depois da auto-encryption'
          : undefined}
        label="Ver query / comando que chegou ao servidor"
      />
    </>
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
  const apiFaixa = useApi()
  const apiTexto = useApi()
  const apiPar = useApi()
  const apiExemplos = useApi()
  const [titulares, setTitulares] = useState([])
  const [cpf, setCpf] = useState('')
  const [resultado, setResultado] = useState(null)
  const [resultadoFaixa, setResultadoFaixa] = useState(null)
  const [par, setPar] = useState(null)
  const [buscaString, setBuscaString] = useState(null)

  const buscar = (params) => apiBusca.call(`/demo/buscar?${new URLSearchParams(params)}`).then(r => r && setResultado(r))
  const buscarFaixa = (params) => apiFaixa.call(`/demo/buscar?${new URLSearchParams(params)}`).then(r => r && setResultadoFaixa(r))
  const buscarTexto = (tipo) => apiTexto.call(`/demo/buscar-string?tipo=${tipo}`).then(r => r && setBuscaString(r))

  // Ninguém decora um CPF. Sem esta lista, a demo começa com alguém digitando
  // um número que não existe e recebendo zero — pelo motivo errado.
  const carregarTitulares = () => {
    return apiExemplos.call('/demo/exemplos').then(dados => {
      const lista = dados?.titulares || []
      setTitulares(lista)
      // Só preenche o que ainda está vazio: uma segunda resposta chegando
      // depois não pode trocar o titular que já está selecionado na tela.
      setCpf(atual => atual || lista[0]?.cpf || '')
    })
  }
  useEffect(() => { carregarTitulares() }, [apiExemplos.call])

  return (
    <div className="app app--simples" data-pov-shell>
      <a className="pov-skip-link" href="#conteudo-principal">Pular para o conteúdo</a>
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

      <main id="conteudo-principal" tabIndex={-1} className="conteudo conteudo--simples">
        <p className="tese">
          <strong>Mesma coleção, duas leituras.</strong> A aplicação tem a chave; o DBA não.
        </p>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>1 · Igualdade sobre CPF cifrado</h3>
          <p className="legenda" style={{ margin: '0 0 8px' }}>
            Titulares na base — selecione um exemplo para buscar:
          </p>
          <div className="chips">
            {titulares.map(t => (
              <button key={t.cpf}
                className={t.cpf === cpf ? 'chip chip--ativo' : 'chip'}
                onClick={() => setCpf(t.cpf)}>
                <strong>{t.nome}</strong>
                <span>{formatarCpf(t.cpf)} · {t.uf} · {brl(t.salario)}</span>
              </button>
            ))}
            {!titulares.length && (apiExemplos.loading
              ? <span className="legenda">carregando titulares…</span>
              : <span className="legenda" role="status">{apiExemplos.error ? 'Não foi possível carregar os titulares.' : 'Nenhum titular disponível.'} <button className="acao acao--secundario" onClick={carregarTitulares}>Recarregar titulares</button></span>)}
          </div>
          <div className="campos" style={{ marginTop: 14 }}>
            <button className="acao" disabled={apiBusca.loading || !cpf}
              onClick={() => buscar({ cpf })}>
              Buscar por igualdade
            </button>
          </div>
          {apiBusca.loading && <p className="legenda" style={{ marginTop: 14 }}>consultando os dois clientes…</p>}
          <Resultado resultado={resultado} />
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>2 · Faixa de salário cifrado, e o controle em claro</h3>
          <div className="campos">
            {[
              ['5–15 mil', 5000, 15000],
              ['15–25 mil', 15000, 25000],
              ['25–40 mil', 25000, 40000],
            ].map(([label, salario_min, salario_max]) => (
              <button key={label} className="acao" disabled={apiFaixa.loading}
                onClick={() => buscarFaixa({ salario_min, salario_max })}>
                Faixa: {label}
              </button>
            ))}
            <button className="acao acao--secundario" disabled={apiFaixa.loading}
              onClick={() => buscarFaixa({ uf: 'SP' })}
              title="Campo em claro: o controle do experimento">
              Buscar por UF (campo em claro)
            </button>
          </div>
          {apiFaixa.loading && <p className="legenda" style={{ marginTop: 14 }}>consultando os dois clientes…</p>}
          <Resultado resultado={resultadoFaixa} />
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>3 · Texto parcial no e-mail cifrado</h3>
          <p className="legenda">
            Escolha um exemplo pronto. O servidor casa o trecho contra o e-mail sem decifrá-lo;
            o trecho que casou aparece marcado no resultado da aplicação.
          </p>
          <div className="chips" role="group" aria-label="Tipo de busca parcial">
            {[
              ['prefixo', 'Começa com', 'titular0'],
              ['sufixo', 'Termina com', '@exemplo.invalid'],
              ['trecho', 'Contém', 'ular0@'],
            ].map(([tipo, label, exemplo]) => (
              <button key={tipo} className={buscaString?.modo === tipo ? 'chip chip--ativo' : 'chip'}
                disabled={apiTexto.loading} onClick={() => buscarTexto(tipo)}>
                <strong>{label}</strong><span>{exemplo}</span>
              </button>
            ))}
          </div>
          {apiTexto.loading && <p className="legenda" style={{ marginTop: 14 }}>consultando os dois clientes…</p>}
          {buscaString && <>
            <div className="aviso" style={{ marginTop: 12 }}><span>ℹ️</span><span><strong>{buscaString.tipo}</strong> — {buscaString.leitura}</span></div>
            <div className="painel-duplo">
              <Painel titulo="SUA APLICAÇÃO" sub="Trecho cifrado pelo driver; resultado decifrado no cliente"
                dados={buscaString.aplicacao} destaque campos={['_id', 'nome', buscaString.campo]}
                marca={{ campo: buscaString.campo, trecho: buscaString.valor, modo: buscaString.modo }}
                aviso={buscaString.aplicacao.encontrados >= buscaString.limite ? `Exibindo os primeiros ${buscaString.limite}.` : undefined} />
              <Painel titulo="O DBA · O BACKUP · A NUVEM" sub="Os mesmos registros por _id, sem acesso à DEK"
                dados={buscaString.dba} campos={['_id', 'nome', buscaString.campo]}
                aviso="Não há como montar esta busca sem a chave: o servidor só casa o trecho com o ciphertext que o driver gera." />
            </div>
            <QueryDetails operation="find" namespace="clientes"
              query={buscaString.enviado_ao_servidor || buscaString.filtro}
              note={buscaString.enviado_ao_servidor
                ? 'como o servidor recebeu, capturado depois da auto-encryption'
                : undefined}
              label="Ver query / comando que chegou ao servidor" />
          </>}
        </div>

        <details className="card card--secondary">
          <summary>Provas adicionais</summary>
          <div className="secondary-content">
          <h2>Alternativas</h2>
          <table>
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

          <h3 style={{ marginTop: 22 }}>Ciphertext randomizado</h3>
          <p className="tese">Mesmo CPF, dois ciphertexts distintos.</p>
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
        </details>

        <p className="legenda" style={{ textAlign: 'center', margin: '8px 0 32px' }}>
          Dado sintético. Os CPF têm dígito verificador válido e prefixo <code>999</code>, uma
          faixa não emitida — não pertencem a ninguém.
        </p>
      </main>

      <ErroToast />
    </div>
  )
}
