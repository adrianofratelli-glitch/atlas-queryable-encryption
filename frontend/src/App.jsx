import React, { lazy, Suspense, useEffect, useState } from 'react'
import { useApi } from './hooks/useApi'

const Cofre       = lazy(() => import('./pages/Cofre'))
const Visoes      = lazy(() => import('./pages/Visoes'))
const Consultas   = lazy(() => import('./pages/Consultas'))
const Fronteiras  = lazy(() => import('./pages/Fronteiras'))
const Shredding   = lazy(() => import('./pages/Shredding'))
const Custo       = lazy(() => import('./pages/Custo'))

const MODULOS = [
  { chave: 'cofre',      num: '01', titulo: 'Cofre de chaves',       sub: 'CMK, DEK e o mapa de campos',            componente: Cofre },
  { chave: 'visoes',     num: '02', titulo: 'Duas visões',           sub: 'a aplicação e o DBA, mesma query',       componente: Visoes },
  { chave: 'consultas',  num: '03', titulo: 'Consulta sobre cifrado', sub: 'igualdade e faixa sobre ciphertext',    componente: Consultas },
  { chave: 'fronteiras', num: '04', titulo: 'Fronteiras',            sub: 'o que não funciona, e por quê',          componente: Fronteiras },
  { chave: 'shredding',  num: '05', titulo: 'Crypto shredding',      sub: 'apagar a chave, não o dado',             componente: Shredding },
  { chave: 'custo',      num: '06', titulo: 'Preço da privacidade',  sub: 'storage e latência, medidos',            componente: Custo },
]

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

/** Selo permanente de estado do ambiente. Um preflight vermelho no palco tem que
 *  aparecer antes de alguém clicar, não depois. */
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

export default function App() {
  const [ativo, setAtivo] = useState(() => {
    const hash = window.location.hash.replace('#/', '').replace('#', '')
    return MODULOS.some(m => m.chave === hash) ? hash : 'visoes'
  })

  useEffect(() => {
    const aoMudar = () => {
      const hash = window.location.hash.replace('#/', '').replace('#', '')
      if (MODULOS.some(m => m.chave === hash)) setAtivo(hash)
    }
    window.addEventListener('hashchange', aoMudar)
    return () => window.removeEventListener('hashchange', aoMudar)
  }, [])

  const modulo = MODULOS.find(m => m.chave === ativo) || MODULOS[1]
  const Pagina = modulo.componente

  return (
    <div className="app">
      <nav className="sidebar" aria-label="Módulos">
        <div className="sidebar__marca">
          <svg aria-hidden="true" width="26" height="26" viewBox="0 0 256 549" fill="none">
            <path d="M175.622 61.108C152.612 33.807 132.797 5.315 128.69.239c-.5-.32-1-.239-1-.239s-.5-.081-1 .239C122.583 5.315 102.768 33.807 79.758 61.108 24.914 128.23 0 188.949 0 245.85c0 68.687 31.064 130.1 79.875 171.037l1.872 1.253c1.522 16.09 4.254 51.884 3.551 75.43 0 0 4.596 3.112 9.94 3.928 5.343.816 11.435.816 11.435.816l-1.114-15.274c8.828 1.952 17.9 3.025 27.22 3.025 9.323 0 18.393-1.073 27.22-3.025l-1.114 15.274s6.093 0 11.435-.816c5.343-.816 9.94-3.928 9.94-3.928-.703-23.546 2.029-59.34 3.55-75.43l1.873-1.253C233.936 375.95 265 314.537 265 245.85c0-56.901-24.914-117.62-89.378-184.742z" fill="#00ED64"/>
          </svg>
          <div>
            <strong>Queryable Encryption</strong>
            <span>consulta sobre dado que o servidor não lê</span>
          </div>
        </div>

        {MODULOS.map(m => (
          <button key={m.chave} className="nav-item" aria-current={m.chave === ativo}
            onClick={() => { window.location.hash = `#/${m.chave}`; setAtivo(m.chave) }}>
            <span className="nav-item__num">{m.num}</span>
            <span>
              {m.titulo}
              <span className="nav-item__sub">{m.sub}</span>
            </span>
          </button>
        ))}

        <div style={{ marginTop: 'auto', padding: '16px 20px 0' }}>
          <SeloPreflight />
        </div>
      </nav>

      <main className="conteudo">
        <Suspense fallback={<p className="legenda">carregando módulo…</p>}>
          <Pagina />
        </Suspense>
      </main>

      <ErroToast />
    </div>
  )
}
