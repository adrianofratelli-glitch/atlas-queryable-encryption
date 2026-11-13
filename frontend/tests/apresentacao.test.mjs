// Testes das regras de apresentação (sem navegador, sem dependência nova):
//   cd frontend && npm test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  avisoTotalString, brl, formatarCpf, posicaoDoTrecho, legendaPainel, leituraPorId,
  textoCifra, redact, vereditoPar,
} from '../src/lib/apresentacao.js'

const raiz = new URL('../../', import.meta.url)
const ler = (caminho) => readFileSync(new URL(caminho, raiz), 'utf8')

test('formatarCpf pontua 11 dígitos e não mexe no resto', () => {
  assert.equal(formatarCpf('99912345678'), '999.123.456-78')
  assert.equal(formatarCpf('999123456789'), '999123456789')
})

test('brl formata número e ignora o que não é número', () => {
  assert.match(brl(15000), /15\.000/)
  assert.equal(brl(undefined), '')
  assert.equal(brl('15000'), '')
})

test('posicaoDoTrecho segue o modo da busca', () => {
  const email = 'titular0042@exemplo.invalid'
  assert.equal(posicaoDoTrecho(email, 'titular0', 'prefixo'), 0)
  assert.equal(posicaoDoTrecho(email, 'exemplo', 'prefixo'), -1)
  assert.equal(posicaoDoTrecho(email, '@exemplo.invalid', 'sufixo'), 11)
  assert.equal(posicaoDoTrecho(email, 'titular0', 'sufixo'), -1)
  assert.equal(posicaoDoTrecho(email, 'ular0', 'trecho'), 3)
  assert.equal(posicaoDoTrecho(email, '', 'trecho'), -1)
})

test('posicaoDoTrecho ignora caixa, como o caseSensitive:false do encryptedFields', () => {
  assert.equal(posicaoDoTrecho('Titular0@Exemplo.invalid', 'titular0', 'prefixo'), 0)
  assert.equal(posicaoDoTrecho('titular0@exemplo.invalid', 'ULAR0@', 'trecho'), 3)
})

test('legendaPainel: o lado sem chave sempre diz "sem a chave"', () => {
  assert.equal(legendaPainel({ encontrados: 1, ms: 210.3 }, true), '1 documento(s) · 210.3 ms')
  assert.equal(legendaPainel({ encontrados: 0, ms: 205 }, false), 'o mesmo filtro, sem a chave: 0 documento(s) · 205 ms')
  // Busca de string: o DBA lê por _id e não tem tempo próprio.
  assert.equal(legendaPainel({ encontrados: 3 }, false), '3 documento(s)')
  assert.equal(legendaPainel(null, false), '')
})

test('leituraPorId só vale para o painel do DBA', () => {
  assert.equal(leituraPorId({ origem: 'por_id' }, false), true)
  assert.equal(leituraPorId({ origem: 'por_id' }, true), false)
  assert.equal(leituraPorId({ origem: 'filtro' }, false), false)
})

test('textoCifra mostra amostra do payload e a DEK, e recusa o que não é subtype 6', () => {
  const v = { __cifrado__: true, subtype: 6, bytes: 133, chave: 'aabbccddeeff00112233', hex: '0011', fim: 'ff' }
  assert.deepEqual(textoCifra(v), { amostra: '0011…ff', rodape: '133 B · subtype 6 · DEK aabbccdd' })
  assert.equal(textoCifra({ __cifrado__: false, subtype: 0, bytes: 4 }), null)
  assert.equal(textoCifra('999.123.456-78'), null)
})

test('redact mascara plaintext sensível em qualquer profundidade, mas nunca o rótulo de ciphertext', () => {
  const comando = {
    find: 'clientes',
    filter: { cpf: { $eq: '<Binary subtype 6 · 172 B · ciphertext>' }, uf: 'SP' },
    dba: { cpf: '99912345678', aninhado: [{ email: 'x@y' }] },
  }
  const r = redact(comando)
  assert.equal(r.filter.cpf.$eq, '<Binary subtype 6 · 172 B · ciphertext>')
  assert.equal(r.filter.uf, 'SP')
  assert.equal(r.dba.cpf, '<mascarado>')
  assert.equal(r.dba.aninhado[0].email, '<mascarado>')
  assert.ok(!JSON.stringify(r).includes('99912345678'))
})

test('avisoTotalString usa o total do countDocuments e cai no limite sem ele', () => {
  const base = { limite: 10 }
  assert.equal(
    avisoTotalString({ ...base, aplicacao: { encontrados: 10, total: 111 } }),
    '111 documentos casam no total; exibindo os primeiros 10.',
  )
  assert.equal(avisoTotalString({ ...base, aplicacao: { encontrados: 3, total: 3 } }), undefined)
  assert.equal(avisoTotalString({ ...base, aplicacao: { encontrados: 10, total: null } }), 'Exibindo os primeiros 10.')
  assert.equal(avisoTotalString(null), undefined)
})

test('vereditoPar nunca afirma "distintos" quando o backend diz que não são', () => {
  assert.equal(vereditoPar({ ciphertexts_distintos: true, leitura: 'ok' }).ok, true)
  assert.equal(vereditoPar({ ciphertexts_distintos: false, leitura: 'x' }).ok, false)
  assert.equal(vereditoPar(null), null)
})

test('contrato: os exemplos de busca de string da tela são os mesmos da allowlist do backend', () => {
  const app = ler('frontend/src/App.jsx')
  const backend = ler('backend/routers/demo.py')
  const tela = [...app.matchAll(/\['(prefixo|sufixo|trecho)', '[^']+', '([^']+)'\]/g)].map((m) => [m[1], m[2]])
  assert.equal(tela.length, 3)
  for (const [modo, valor] of tela) {
    const bloco = new RegExp(`"${modo}": \\{[^}]*"valor": "([^"]+)"`).exec(backend)
    assert.ok(bloco, `modo ${modo} ausente em BUSCAS_STRING`)
    assert.equal(bloco[1], valor, `exemplo de ${modo} divergente entre tela e backend`)
  }
})

test('contrato: os três cards mantêm estado próprio (invariante do AGENTS.md)', () => {
  const app = ler('frontend/src/App.jsx')
  for (const estado of ['setResultado', 'setResultadoFaixa', 'setBuscaString']) {
    assert.match(app, new RegExp(`\\b${estado}\\b`))
  }
  // A faixa não pode escrever no estado da igualdade.
  assert.doesNotMatch(app, /buscarFaixa[^\n]*setResultado\(/)
})
