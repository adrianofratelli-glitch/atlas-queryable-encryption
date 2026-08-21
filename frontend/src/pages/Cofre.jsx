import React, { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import Bloco from '../components/Bloco'

/** Módulo 01 — a hierarquia de chaves, de cima a baixo. */
export default function Cofre() {
  const api = useApi()
  const [kms, setKms] = useState(null)
  const [deks, setDeks] = useState(null)
  const [mapa, setMapa] = useState(null)
  const [rotacao, setRotacao] = useState(null)
  const [ocupado, setOcupado] = useState(false)

  const carregar = () => {
    api.call('/cofre/kms').then(setKms)
    api.call('/cofre/deks').then(setDeks)
    api.call('/cofre/mapa').then(setMapa)
  }
  useEffect(() => { carregar() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const rotacionar = async () => {
    setOcupado(true)
    setRotacao(await api.call('/cofre/rotacionar-cmk', { method: 'POST' }))
    setOcupado(false)
    carregar()
  }

  return (
    <>
      <div className="kicker">módulo 01</div>
      <h1>Cofre de chaves</h1>
      <p className="tese">
        Três níveis. A CMK vive no KMS e nunca sai de lá. A DEK fica guardada
        <strong> cifrada pela CMK</strong> dentro do próprio MongoDB — e isso é seguro
        precisamente porque o MongoDB não tem a chave que a abre. O campo é cifrado pela
        DEK, no cliente, antes de sair pela rede.
      </p>

      {kms && (
        <div className="card">
          <h2>Provedor de KMS</h2>
          <div className="grade grade--3" style={{ marginTop: 12 }}>
            <div className="metrica">
              <div className="metrica__valor" style={{ fontSize: 18 }}>{kms.provedor}</div>
              <div className="metrica__rotulo">provedor ativo</div>
            </div>
            <div className="metrica">
              <div className="metrica__valor" style={{ fontSize: 14 }}>{kms.cmk || '—'}</div>
              <div className="metrica__rotulo">CMK</div>
            </div>
            <div className="metrica">
              <div className="metrica__valor" style={{ fontSize: 14 }}>{kms.cofre_namespace}</div>
              <div className="metrica__rotulo">namespace do cofre</div>
            </div>
          </div>
          {kms.aviso && <div className="aviso"><span>⚠️</span><span>{kms.aviso}</span></div>}
          <p className="legenda" style={{ marginTop: 12 }}>{kms.nota_separacao}</p>
        </div>
      )}

      {deks && (
        <div className="card">
          <h2>DEKs no cofre <span className="selo">{deks.total}</span></h2>
          <table style={{ marginTop: 12 }}>
            <thead>
              <tr><th>nome</th><th>id</th><th>provedor</th><th>criada em</th><th>material</th></tr>
            </thead>
            <tbody>
              {deks.deks.map(dek => (
                <tr key={dek.id}>
                  <td>{dek.nomes.join(', ') || <span className="legenda">sem nome</span>}</td>
                  <td className="num" style={{ fontSize: 11 }}>{dek.id}</td>
                  <td>{dek.provedor}</td>
                  <td className="num">{dek.criada_em?.slice(0, 10)}</td>
                  <td>
                    <span className="cifra">{dek.material_amostra}</span>
                    <span className="cifra__bytes">{dek.material_bytes} B</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="legenda" style={{ marginTop: 10 }}>
            O <code>keyMaterial</code> está cifrado pela CMK — o MongoDB nunca vê este material
            em claro. Esta é uma coleção comum, e é por isso que roubar o banco inteiro não basta.
          </p>
        </div>
      )}

      {mapa && (
        <div className="card">
          <h2>Mapa de campos</h2>
          <table style={{ marginTop: 12 }}>
            <thead>
              <tr><th>campo</th><th>tipo</th><th>consulta</th><th>contention</th><th>faixa</th></tr>
            </thead>
            <tbody>
              {mapa.cifrados.map(campo => (
                <tr key={campo.campo}>
                  <td><span className="cifra">{campo.campo}</span></td>
                  <td className="num">{campo.tipo}</td>
                  <td>{campo.consulta}</td>
                  <td className="num">{campo.contention ?? '—'}</td>
                  <td className="num">{campo.faixa ? `${campo.faixa.min} – ${campo.faixa.max}` : '—'}</td>
                </tr>
              ))}
              {mapa.claros.map(campo => (
                <tr key={campo}>
                  <td>{campo}</td>
                  <td colSpan={4} className="legenda">em claro — criptografia é por campo, não pela coleção</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="aviso"><span>ℹ️</span><span>{mapa.nota_observacoes}</span></div>
          <div className="aviso aviso--perigo"><span>⚠️</span><span>{mapa.nota_imutabilidade}</span></div>
        </div>
      )}

      <div className="card">
        <h2>Rotação de CMK</h2>
        <p className="tese">
          Rotacionar a CMK recifra as <strong>DEKs</strong> — barato e instantâneo. Ela
          <strong> não</strong> recifra os campos: eles continuam cifrados pelas mesmas DEKs,
          que apenas passaram a ser guardadas sob outro envelope. Recifrar campo exigiria
          reescrever a coleção inteira.
        </p>
        <button className="acao acao--secundario" style={{ marginTop: 12 }} disabled={ocupado} onClick={rotacionar}>
          {ocupado ? 'rotacionando…' : 'Rotacionar CMK'}
        </button>
        {rotacao && (
          <>
            <div className="grade grade--2" style={{ marginTop: 14 }}>
              <div className="metrica">
                <div className="metrica__valor" style={{ color: 'var(--accent)' }}>{rotacao.deks_recifradas}</div>
                <div className="metrica__rotulo">DEKs recifradas</div>
              </div>
              <div className="metrica">
                <div className="metrica__valor">{rotacao.campos_recifrados}</div>
                <div className="metrica__rotulo">campos recifrados</div>
              </div>
            </div>
            <p className="legenda" style={{ marginTop: 10 }}>{rotacao.nota}</p>
          </>
        )}
        <Bloco dados={kms} rotulo="Ver resposta bruta do provedor" />
      </div>
    </>
  )
}
