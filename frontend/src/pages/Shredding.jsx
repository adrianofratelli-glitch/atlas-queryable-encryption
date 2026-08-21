import React, { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import Documento from '../components/Documento'
import Bloco from '../components/Bloco'

/**
 * Módulo 05 — crypto shredding.
 *
 * O passo 3 (cache limpo) aparece como PASSO, não como detalhe de implementação.
 * É ele que explica por que o documento ainda abriu por alguns segundos, e
 * transformá-lo em passo visível é a diferença entre "achei que estava quebrado"
 * e "entendi o cache".
 *
 * A demo opera na coleção da COORTE. Apagar uma DEK de `clientes` derruba os
 * módulos 02, 03, 04 e 06 até um reseed completo.
 */
const COORTE = 'clientes_tenant_beta'
const PASSOS = [
  'documento legível',
  'DELETE da DEK do campo',
  'cache de DEK limpo (cliente recriado)',
  'reler o documento',
]

export default function Shredding() {
  const apiEscopos = useApi()
  const apiTitular = useApi()
  const apiExecutar = useApi()
  const apiVerificar = useApi()
  const apiContraprova = useApi()

  const [escopos, setEscopos] = useState(null)
  const [docId, setDocId] = useState('')
  const [titular, setTitular] = useState(null)
  const [campo, setCampo] = useState('cpf')
  const [confirmacao, setConfirmacao] = useState('')
  const [execucao, setExecucao] = useState(null)
  const [verificacao, setVerificacao] = useState(null)
  const [contraprova, setContraprova] = useState(null)

  const carregarEscopos = () => apiEscopos.call('/shredding/escopos').then(setEscopos)
  useEffect(() => { carregarEscopos() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const passoAtual = !execucao ? (titular ? 1 : 0) : (verificacao ? 4 : 3)

  return (
    <>
      <div className="kicker">módulo 05</div>
      <h1>Crypto shredding</h1>
      <p className="tese">
        Apagar a DEK torna todo campo cifrado por ela <strong>matematicamente irrecuperável</strong>,
        inclusive nos backups já feitos e nas réplicas já propagadas. É o direito ao esquecimento
        sem <code>delete</code>: o registro continua existindo e contabilizável, o conteúdo pessoal
        não é mais legível por ninguém — o que resolve o conflito entre a retenção obrigatória do
        Bacen e a LGPD art. 18.
      </p>
      <div className="aviso" style={{ display: 'block' }}>
        <strong>A granularidade não é livre.</strong> Com auto-encryption a chave é ligada por
        campo de uma coleção, nunca por documento — e o Queryable Encryption exige uma DEK
        distinta por campo. Disso saem dois escopos possíveis, e só dois.
      </div>

      {escopos && (
        <div className="card">
          <h2>Escopos de shredding</h2>
          <div className="grade grade--3" style={{ marginTop: 12 }}>
            {escopos.escopos.map(item => (
              <div key={item.chave} className="metrica">
                <div className="metrica__rotulo">{item.titulo}</div>
                <p className="legenda" style={{ marginTop: 8 }}>{item.como}</p>
                <p className="legenda"><strong>Esquecimento:</strong> {item.esquecimento}</p>
                <p className="legenda"><strong>Custo:</strong> {item.custo}</p>
              </div>
            ))}
          </div>
          <h3 style={{ marginTop: 18 }}>Chaves vivas no cofre</h3>
          <table style={{ marginTop: 8 }}>
            <thead><tr><th>coleção</th><th>campos com DEK viva</th></tr></thead>
            <tbody>
              {Object.entries(escopos.chaves_vivas).map(([colecao, campos]) => (
                <tr key={colecao}>
                  <td>{colecao}</td>
                  <td>{campos.length ? campos.join(' · ') : <span className="legenda">nenhuma</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card">
        <h2>Linha do tempo</h2>
        <div className="passos" style={{ marginTop: 12 }}>
          {PASSOS.map((texto, indice) => (
            <div key={texto} className={indice < passoAtual ? 'passo passo--feito' : 'passo'}>
              <span className="passo__num">{indice + 1}</span>
              <span>{texto}</span>
              {indice === 2 && (
                <span className="legenda" style={{ marginLeft: 'auto', maxWidth: 380, textAlign: 'right' }}>
                  o driver mantém a DEK decifrada em memória (padrão 60 s) — sem esta limpeza o
                  documento continua abrindo e a demo parece falhar
                </span>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h2>1 · Documento legível</h2>
        <p className="legenda">Coleção da coorte: <code>{COORTE}</code></p>
        <div className="campos" style={{ marginTop: 12 }}>
          <div className="campo">
            <label htmlFor="docid">_id do titular</label>
            <input id="docid" value={docId} onChange={e => setDocId(e.target.value.trim())} style={{ width: 260 }} />
          </div>
          <button className="acao" disabled={apiTitular.loading || docId.length !== 24}
            onClick={() => apiTitular.call(`/shredding/titular/${docId}?colecao=${COORTE}`).then(setTitular)}>
            {apiTitular.loading ? 'lendo…' : 'Ler titular'}
          </button>
        </div>
        {titular && (
          <div className="painel-duplo" style={{ marginTop: 16 }}>
            <div className="painel painel--app">
              <div className="painel__titulo">▚ Aplicação</div>
              <div className="painel__origem">{titular.legivel ? 'legível' : 'ilegível'}</div>
              {titular.legivel
                ? <Documento doc={titular.aplicacao} />
                : <Bloco dados={titular.erro} rotulo="Ver erro" erro />}
            </div>
            <div className="painel painel--dba">
              <div className="painel__titulo">▚ DBA</div>
              <div className="painel__origem">o documento continua no banco</div>
              <Documento doc={titular.dba} />
            </div>
          </div>
        )}
      </div>

      <div className="card">
        <h2>2 e 3 · Apagar a DEK do campo</h2>
        <div className="aviso aviso--perigo">
          <span>⚠️</span>
          <span>
            Irreversível. O efeito alcança réplicas e backups já feitos: sem a DEK, o ciphertext
            não é decifrável por ninguém, em lugar nenhum.
          </span>
        </div>
        <div className="campos" style={{ marginTop: 14 }}>
          <div className="campo">
            <label htmlFor="campo">campo</label>
            <select id="campo" value={campo} onChange={e => setCampo(e.target.value)}>
              {['cpf', 'email', 'salario', 'score_credito', 'observacoes'].map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <div className="campo">
            <label htmlFor="conf">confirme digitando <code>{COORTE}</code></label>
            <input id="conf" value={confirmacao} onChange={e => setConfirmacao(e.target.value.trim())} style={{ width: 260 }} />
          </div>
          <button className="acao acao--perigo" disabled={apiExecutar.loading || confirmacao !== COORTE}
            onClick={() => apiExecutar.call('/shredding/executar', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ colecao: COORTE, campos: [campo], confirmacao }),
            }).then(r => { setExecucao(r); carregarEscopos() })}>
            {apiExecutar.loading ? 'apagando…' : 'Apagar DEK'}
          </button>
        </div>
        {execucao && (
          <>
            <p className="legenda" style={{ marginTop: 12 }}>{execucao.alcance}</p>
            <Bloco dados={execucao.deks_apagadas} rotulo="Ver DEKs apagadas" />
          </>
        )}
      </div>

      <div className="card">
        <h2>4 · Reler</h2>
        <button className="acao" disabled={apiVerificar.loading || docId.length !== 24}
          onClick={() => apiVerificar.call(`/shredding/verificar/${docId}?colecao=${COORTE}&campo=${campo}`).then(setVerificacao)}>
          {apiVerificar.loading ? 'lendo…' : 'Reler o mesmo documento'}
        </button>

        {verificacao && (
          <>
            <div className="painel-duplo" style={{ marginTop: 16 }}>
              <div className="painel painel--dba">
                <div className="painel__titulo">▚ Leitura completa</div>
                <div className="painel__origem">find(&#123;_id&#125;)</div>
                <span className={verificacao.leitura_completa.ok ? 'selo selo--aviso' : 'selo selo--ok'}>
                  {verificacao.leitura_completa.ok ? 'ainda legível' : '✓ falha — chave ausente'}
                </span>
                {verificacao.leitura_completa.erro &&
                  <Bloco dados={verificacao.leitura_completa.erro} rotulo="Ver erro do driver" erro />}
              </div>
              <div className="painel painel--app">
                <div className="painel__titulo">▚ Leitura sem o campo</div>
                <div className="painel__origem">find(&#123;_id&#125;, &#123;{campo}: 0&#125;)</div>
                <span className={verificacao.leitura_sem_o_campo.ok ? 'selo selo--ok' : 'selo selo--erro'}>
                  {verificacao.leitura_sem_o_campo.ok ? '✓ o resto continua legível' : 'falhou'}
                </span>
                {verificacao.leitura_sem_o_campo.documento &&
                  <Documento doc={verificacao.leitura_sem_o_campo.documento} />}
              </div>
            </div>
            <div className="aviso" style={{ display: 'block' }}>
              {verificacao.nota}
            </div>
          </>
        )}
      </div>

      <div className="card">
        <h2>Contraprova: a coorte vizinha</h2>
        <p className="tese">
          Um shredding que derruba o inquilino errado não é privacidade, é incidente. Esta é a
          única evidência que separa “apaguei a chave certa” de “apaguei alguma chave”.
        </p>
        <button className="acao acao--secundario" style={{ marginTop: 12 }} disabled={apiContraprova.loading}
          onClick={() => apiContraprova.call('/shredding/contraprova').then(setContraprova)}>
          {apiContraprova.loading ? 'verificando…' : 'Verificar as duas coleções'}
        </button>
        {contraprova && (
          <>
            <table style={{ marginTop: 14 }}>
              <thead><tr><th>coleção</th><th>leitura completa</th></tr></thead>
              <tbody>
                {Object.entries(contraprova.colecoes).map(([nome, estado]) => (
                  <tr key={nome}>
                    <td>{nome}</td>
                    <td>
                      <span className={estado.legivel ? 'selo selo--ok' : 'selo selo--aviso'}>
                        {estado.legivel ? '✓ legível' : 'chave ausente'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="legenda" style={{ marginTop: 10 }}>{contraprova.nota}</p>
          </>
        )}
        <p className="legenda" style={{ marginTop: 14 }}>
          Para repor: <code>python scripts/criar-cofre.py</code> e
          <code> python backend/seed_data.py --drop</code>. O seed é determinístico.
        </p>
      </div>
    </>
  )
}
